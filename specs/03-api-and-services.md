# 03 — API and Service Structure

The HTTP surface, the streaming protocol, how the code is partitioned into services
today, and what splitting it apart would actually involve.

---

## Current shape: a modular monolith

One FastAPI process serves everything. That is a deliberate choice for a system at
this stage, not an accident waiting to be corrected.

```
FastAPI process (port 8000)
├── HTTP layer          api.py            routes, validation, SSE, auth
├── Orchestration       graph.py          agent wiring
│                       orchestrator.py   routing
│                       state.py          shared state contract
├── Agents              agents/*.py       one module per agent
├── Domain logic        agents/selection.py   filtering and extraction
├── Model client        llm.py            single shared Gemini client
├── Data access         database.py       SQLAlchemy models and helpers
├── Catalog             data/catalog.py   JSON loaded at import
└── Evaluation          evals/*.py        cases, scorers, runner, report

React SPA (port 5173) — separate dev server, talks to the API over CORS
```

The boundaries between those blocks are already clean: agents import `llm` and
`data.catalog`, never `api`. `api.py` imports the graph, never an individual agent's
internals. Nothing imports upward. That discipline is what makes a future split
mechanical rather than archaeological.

---

## Endpoint reference

### Catalog

**`GET /api/sneakers`**

Full catalog with optional, combinable filters. No model calls, no auth.

| Param | Type | Behavior |
| --- | --- | --- |
| `q` | string | Substring match across name + brand + colorway |
| `brand` | string | Exact match, case-insensitive |
| `profile` | string | `low` / `mid` / `high` |
| `max_price` | float | Retail price ceiling |
| `in_stock` | bool | Filters on the catalog's static `in_stock` flag |

Returns a list of catalog objects with `name` prepended. See
[04-data-schema.md](04-data-schema.md#catalog-entry).

Note: this route filters on the *static* `in_stock` field from the JSON, while the
agents query live database quantity. Browse and recommend can therefore disagree about
availability. Reconciling them is listed under known gaps below.

---

### Agent pipeline

**`POST /api/agent`** — SSE stream

Runs the full LangGraph pipeline, streaming each agent's completion the moment it
finishes.

Request:
```json
{
  "input":    "low top jordans under $150",
  "wardrobe": ["Nike Air Force 1 Low '07 White"],
  "brands":   ["Jordan"],
  "colors":   ["black"]
}
```

All fields except `input` are optional. `brands` and `colors` come from UI filter
chips and take priority over anything parsed from the text. `wardrobe`, when present,
skips the database lookup in `inventory_agent`.

Stream events:
```
data: {"type":"agent_step","node":"orchestrator","label":"Orchestrator",
       "summary":"Routing to Sneaker Advisor","reasoning":"...","next":"sneaker_agent"}

data: {"type":"result","sneakers":[{...}],"output":"Sneaker Availability Report..."}

data: [DONE]
```

On failure: `{"type":"error","message":"..."}` followed by `[DONE]`. The stream always
terminates with `[DONE]`, error or not, so the client has one teardown path.

`sneakers` in the result event carries full catalog details plus *live* `quantity` and
`in_stock`, re-queried after the graph finishes rather than reusing the values the
logistics agent saw.

---

### Evaluation

**`POST /api/evals/run`** — SSE stream, admin only

Request (both fields optional):
```json
{ "case_id": "TC-003", "custom_input": "cheapest new balance" }
```

`custom_input` wins when both are set, and runs a one-off scenario with no fixed
expectations — scored only on dimensions that do not need one.

Returns `403` for a non-admin session. The check lives in the route handler, not just
in the UI, so a direct API call is rejected identically. Event shapes are in
[04-data-schema.md](04-data-schema.md#eval-sse-events).

---

### Auth

| Endpoint | Behavior |
| --- | --- |
| `POST /api/auth/login` | Verifies credentials, writes `username` and `is_admin` into a signed session cookie |
| `POST /api/auth/logout` | Clears the session |
| `GET /api/auth/me` | Returns the session user, or `401` |

Login returns `401` for every failure mode — unknown user, no password set, wrong
password — without distinguishing which. Distinguishing them turns the login form into
a username enumeration oracle.

`GET /api/auth/me` is what lets the SPA restore auth state after a page refresh
without keeping a token in `localStorage`.

---

### Users and wardrobe

| Endpoint | Behavior |
| --- | --- |
| `GET /api/users` | All users with wardrobe counts |
| `GET /api/users/{username}` | One user's profile and full wardrobe |
| `POST /api/users/{username}/wardrobe` | Adds a sneaker; creates the user if absent; duplicates are no-ops |
| `DELETE /api/users/{username}/wardrobe/{sneaker_name}` | Removes one sneaker |

These routes take the username from the path and do not check the session against it.
See known gaps.

---

### Inventory and transactions

**`GET /api/inventory/{sneaker_name}`** — live quantity for one sneaker.

**`POST /api/inventory/purchase`** — session required.
```json
{ "sneaker_name": "Jordan 4 Retro SB Pine Green", "username": "john" }
```
Decrements stock by one and adds to the wardrobe. `409` if out of stock.

**`POST /api/bid`** — session required.
```json
{ "sneaker_name": "Jordan 4 Retro SB Pine Green", "bid_amount": 300.0, "username": "john" }
```

Response:
```json
{ "accepted": true, "reasoning": "The $300 bid sits just under the $325 lowest ask...",
  "purchased": true, "quantity": 0 }
```

An accepted bid buys immediately — same code path as a flat-price purchase. `409` if
the pair sells out between evaluation and purchase, which is a real race with a
several-second window while the model call is in flight, and reporting it as a race
rather than a rejection matters to the shopper.

The session check runs *before* `evaluate_bid`, so an unauthenticated request never
costs a model call.

---

## The streaming design

Both long-running endpoints use the same pattern, and it exists to solve a specific
problem: LangGraph's `.stream()` is synchronous, but FastAPI's response generator is
async. Calling the sync function directly inside the async generator blocks the event
loop, which stalls every other request on the server.

```
async generator (event loop)          background thread
        │                                     │
        │                              graph.stream(...)
        │                                     │
        │◄──── asyncio.Queue ────── loop.call_soon_threadsafe(
        │      (thread-safe)              queue.put_nowait, chunk)
        │                                     │
   yield SSE event                            │
        │                                     ▼
        ▼                                  ("done", ...)
   yield [DONE]
```

`loop.call_soon_threadsafe` is the piece that makes it correct — it is the only
sanctioned way to hand work from a non-async thread back into a running event loop.
Putting items on the queue directly from the thread would be a race.

Why streaming at all: the pipeline takes 10–30 seconds. A request that returns nothing
for 25 seconds and then everything at once reads as broken, and users abandon it. The
same total wait, with five progress events showing which agent is working and why,
reads as a system thinking. The reasoning text streamed alongside each step turns dead
wait into something worth watching.

Three headers matter on both streams:

| Header | Purpose |
| --- | --- |
| `Cache-Control: no-cache` | Stops intermediaries caching a partial stream |
| `X-Accel-Buffering: no` | Tells nginx not to buffer, which would defeat streaming entirely |
| `Access-Control-Allow-Origin` | Set explicitly — SSE and CORS interact awkwardly |

---

## Auth and session model

| Aspect | Implementation |
| --- | --- |
| Password storage | PBKDF2-HMAC-SHA256, 260,000 iterations, 16-byte random per-user salt, stored as `salt_hex$hash_hex` |
| Verification | `hmac.compare_digest` — constant time, so response timing leaks nothing about how much of the hash matched |
| Session | Starlette `SessionMiddleware`, signed cookie, `same_site=lax` |
| Secret | `SESSION_SECRET` from env; falls back to a per-process random key with a startup warning |
| Roles | `is_admin` boolean, checked in the eval route handler |

The `SESSION_SECRET` fallback is a real operational decision, not a stub. Without the
env var, sessions do not survive a restart and the server says so loudly at boot.
Silently generating a key and letting everyone get logged out on the next deploy is
the failure mode that produces a confusing bug report.

260,000 iterations is OWASP's current floor for PBKDF2-HMAC-SHA256. It is a
deliberate cost — verification takes measurable milliseconds, which is the point,
because it applies to an attacker's offline guessing too.

---

## Concurrency and state

| Concern | Current handling |
| --- | --- |
| Request handling | Async FastAPI; blocking work pushed to threads |
| Session storage | Signed cookie — nothing server-side, so any process can serve any request |
| Database | SQLite with `check_same_thread=False`, one shared engine |
| Transactions | `get_session()` context manager: commit on success, rollback on exception, always close |
| Graph instance | Rebuilt per request in `/api/agent`; built once per eval run |

The session design is the part that is already production-shaped. Signed cookies mean
no server-side session store, so the API is horizontally scalable as-is for auth
purposes. The database is what is not.

---

## Known gaps

Documented rather than hidden, because a spec that only lists strengths is not a spec.

| Gap | Impact | Fix |
| --- | --- | --- |
| Wardrobe routes take username from the path without checking the session | A logged-in user can read or modify another user's wardrobe | Derive the username from the session; reject a mismatch |
| `purchase` and `bid` accept a client-supplied `username` in the body | A logged-in user can buy into someone else's wardrobe | Same fix — session is the source of truth for identity |
| `POST /api/agent` requires no session | Unauthenticated traffic can spend model calls | Require a session; add per-user rate limiting |
| No rate limiting anywhere | A loop against `/api/agent` is a denial-of-wallet attack | Per-user and per-IP limits at the edge |
| `GET /api/sneakers` filters on static `in_stock`, agents use live quantity | Browse and recommend can disagree | Have the catalog route join live inventory |
| `purchase_sneaker` reads then writes without row locking | Two concurrent buyers of the last unit could both succeed | `SELECT ... FOR UPDATE` on Postgres, or an atomic conditional update |
| CORS pinned to `localhost:5173` | Only works locally | Environment-driven origin list |
| Graph rebuilt per request | Small avoidable latency | Build once at startup |

The concurrency gap is worth being precise about. SQLite serializes writes at the file
level, which makes the read-then-write in `purchase_sneaker` safe under the
single-process local pattern this runs in. It stops being safe the moment there are
two processes or a real database, and the fix belongs to that migration.

---

## Extraction plan: what real microservices would look like

Not needed now. Here is the seam map if it were, ordered by which one earns its
independence first.

### Service 1 — Agent service

`graph.py`, `orchestrator.py`, `agents/`, `llm.py`, `state.py`

**Why this one splits first.** It has a completely different resource profile from
everything else: 10–30 seconds per request, dominated by an outbound network call,
and its cost is denominated in tokens rather than CPU. It should scale on concurrent
in-flight model calls, and it should be able to fall over — model provider outage, rate
limit — without taking catalog browsing down with it.

Needs from other services: catalog reads, live stock reads. Both are read-only and
cacheable, which is what makes the seam clean.

### Service 2 — Catalog service

`data/catalog.py`, `GET /api/sneakers`, image backfill

**Why.** Read-heavy, high-volume, trivially cacheable, and it never writes anything.
It is the natural CDN/read-replica candidate and has the opposite scaling curve to the
agent service.

### Service 3 — Commerce service

`database.py`, inventory routes, purchase, wardrobe

**Why.** The only service that owns transactional state. It needs the strongest
consistency guarantees and the strictest access control, and isolating it keeps the
number of places that can corrupt inventory to one.

### Service 4 — Identity service

`auth.py`, session routes

**Why.** Standard extraction target, usually replaced outright by a managed identity
provider rather than kept in-house.

### Service 5 — Evaluation service

`evals/`

**Why.** Batch, offline, no user traffic. Runs on a schedule in CI, not per request.
Belongs on different infrastructure with different uptime expectations, and it needs
to be able to hammer the agent service without competing with real customers.

### What splitting would cost

Honest accounting, since this is the part usually left out:

- Catalog reads become network calls, so the agent service needs a local cache and a
  stale-data policy.
- Stock checks become network calls inside a loop over picks. That is an N+1 across a
  service boundary and would need batching.
- Purchase-after-accepted-bid spans two services, so the race window widens from
  milliseconds to a network round trip. Compensating transactions or an outbox pattern.
- Five deploy pipelines, five sets of dashboards, distributed tracing to answer "why
  was that request slow".

None of that is worth paying until one component's scaling needs actually diverge from
the others'.

---

## Production changes required before real traffic

Grouped by what they protect against.

**Correctness under concurrency**
- SQLite → Postgres with connection pooling. The SQLAlchemy models port by changing
  one URL; the transactional semantics do not port for free.
- Atomic stock decrement with row-level locking.

**Abuse and cost control**
- Auth on `/api/agent`; per-user and per-IP rate limits.
- A per-account token budget with alerting.

**Correct identity handling**
- Session-derived identity on every write route. Never trust a username in a body.

**Operability**
- Structured JSON logging with a request ID threaded through every agent.
- Latency histograms per agent node — the eval harness measures this offline already,
  so the metric definitions exist.
- Token spend per request, per user, per day.
- Health check that verifies model reachability, not just process liveness.

**Deployment**
- Containerize; move every constant currently in code — `MAX_CATALOG_SIZE`,
  `MAX_CRITIQUE_ATTEMPTS`, latency thresholds, CORS origins — into environment
  configuration.
- Frontend served as static assets from a CDN rather than a dev server.

---

## Business impact, if this shipped

**Streaming is a conversion mechanic, not a UI flourish.** Abandonment on a
25-second blank screen is severe. The same wait with visible reasoning holds attention,
and the reasoning text itself builds confidence in the recommendation the shopper is
about to act on. The engineering cost was one thread and one queue.

**The auth gaps are exactly the class of bug that ships.** They are listed here
because a spec that hides them guarantees they reach production. Client-supplied
identity on a write route is one of the most common real-world vulnerabilities, and it
is invisible in a demo where one person is logged in.

**Rate limiting on an LLM endpoint is a financial control.** Every unauthenticated
`/api/agent` call costs money. Without a limit, a script is a bill. This is the newest
item on the standard production checklist and the one most often missing, because the
traditional version of this concern was CPU — which is cheap — rather than tokens,
which are not.

**The monolith is the right call today, and the seams are why.** Clean import
boundaries mean extraction is a refactor rather than a rewrite. The value of that
discipline shows up only on the day it is needed, which is precisely why it has to be
maintained on the days it is not.
