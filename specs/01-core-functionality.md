# 01 — Core Functionality

Every user-facing flow, and the rules each agent follows inside it.

---

## The five agents

Four run inside the LangGraph pipeline. One runs outside it.

| Agent | Job | LLM calls | Runs in graph |
| --- | --- | --- | --- |
| `orchestrator` | Picks which specialist handles the request | 0 or 1 | yes (entry point) |
| `sneaker_agent` | Resolves constraints, filters the catalog, selects picks | 1 | yes |
| `critique_agent` | Reviews picks; approves or sends back one retry | 0 or 1 | yes |
| `logistics_agent` | Live stock check and price reporting | 0 | yes |
| `inventory_agent` | Reviews the user's collection, decides whether to also shop | 2 | yes |
| `bid_agent` | Judges whether an offer on one pair is fair | 0 or 1 | no — standalone |

Each agent is a plain Python function that takes the shared state, does one job, and
returns a dict of only the fields it changed. LangGraph merges that dict back into
state and calls the router to decide what runs next.

---

## Flow 1 — Shopping (the primary path)

**Trigger:** A recommendation request. *"Show me some clean low tops under $200."*

**Route:** `orchestrator → sneaker_agent → critique_agent → logistics_agent → END`

### Step by step

**1. Orchestrator routes.**
A regex pre-check runs first, looking for language about the *existing* collection
("what do I already own", "show me my collection"). If it matches, routing goes
straight to `inventory_agent` with no model call. Otherwise the LLM picks between
`sneaker_agent`, `inventory_agent`, and `logistics_agent`. An unrecognized answer
falls back to `sneaker_agent`.

**2. Sneaker agent resolves constraints.**
Constraints arrive two ways, and structured beats prose:

| Source | Path |
| --- | --- |
| UI filter chips | `requested_brands` / `requested_colors` arrive as structured state fields |
| Free text | The same constraints are parsed out of the sentence by `extract_*` helpers |

An explicit chip selection is a stronger signal than a phrase in a sentence, so
structured fields win when both are present. When they are absent — the Advisor's
free-text box, the admin scenario panel, the CLI — the prose is parsed instead.

Seven constraint types are extracted:

| Constraint | Example phrasing | Enforcement |
| --- | --- | --- |
| Brand | "jordans", "New Balance" | Hard filter |
| Colorway | "black", "grey" (matches "gray"), "cream" (matches "sail", "bone") | Soft preference — falls back |
| Silhouette | "low top", "highs", "mids" | Hard filter |
| Price ceiling | "under $150", "300 dollars max", "I have 250 bucks" | Hard filter |
| Release year | "after 2022", "post-2022", "2023 or later" | Hard filter |
| Ordering | "most expensive", "cheapest" | Changes sort, not membership |
| Pick count | "just 2 options", "give me three" | Passed to the prompt and checked afterward |

Two extraction rules that matter more than they look:

- **Negation flips a brand mention.** "no jordans", "anything but adidas", and
  "I already own nikes" all name a brand the shopper does *not* want. Treating those
  as filters would invert the request. The parser looks back to the nearest sentence
  boundary for a negation phrase and skips the match if it finds one.
- **A bare number is never a price.** "$150" is a price. "150 dollars" is a price.
  "150" on its own is not — otherwise "sneakers with 3 stripes" parses as a $3 budget.
  A number counts as a ceiling only with a currency marker or an explicit ceiling
  phrase in front of it.

**3. Sneaker agent filters, in this order.**

```
1,668 sneakers
  → drop everything out of stock (live DB query)
  → hard filter: brand
  → hard filter: silhouette
  → hard filter: retail price ceiling
  → hard filter: release year floor
  → soft prefer: colorway  (falls back to full pool if nothing matches)
  → sort: by retail price if a superlative was asked for, else by popularity
  → cap at 80 rows
```

Order is load-bearing in two places. Colorway is soft because colorway data is missing
across large parts of the catalog — a hard filter would return nothing for most color
requests, so it falls back to the full pool and the prompt is told plainly that no
confirmed color match exists. And sorting happens *before* the cap, because a
superlative query's correct answer would otherwise be pushed outside the 80-row window
by the default popularity ranking.

Two exclusion rules protect against unverifiable matches:
- A retail price of `0` means *unknown*, not *free*. Ten catalog entries have one.
  They are excluded when a ceiling is set, and they sort last in either price ordering
  — otherwise "what's your cheapest sneaker" answers with a shoe nobody priced.
- A missing release date is excluded when a year floor is set. An unknown date cannot
  be confirmed to satisfy "released after 2022".

**4. Empty pool short-circuits.**
When nothing survives filtering, the agent returns no picks, sets `no_matches = True`,
and writes a message naming the failing combination: *"No in-stock sneakers matched
brand(s) Jordan, low-top, under $80."* The `no_matches` flag tells `critique_agent`
to skip its retry loop — a retry cannot conjure a match the catalog does not hold, and
retrying would burn two more model calls before replacing that specific explanation
with a generic "picks approved".

**5. Sneaker agent selects.**
The surviving pool goes into the prompt as one line per sneaker (name, brand,
colorway, retail, market, profile). Every filter already applied is stated in the
prompt as a *fact*, not a request — "all options are low-top silhouettes", "all
options retail at $150 or less". The model does not need to enforce a constraint the
pool cannot violate, and telling it to would only invite second-guessing.

The requested count defaults to 5 and is clamped to the pool size. Asking a model to
"pick exactly 5" from a pool of 2 is an impossible instruction that produces an
endless critique/retry loop; the target is lowered and the prompt says why.

**6. The answer is validated against the pool.**
The model's response is intersected with the candidate list it was shown. Names that
were not in that list are dropped, whether they are hallucinated or real-but-unoffered.
This is the guardrail that makes catalog validity a property of the code rather than a
hope about the prompt.

**7. Critique agent reviews.**

Deterministic checks first, no model call:

| Check | Failure action |
| --- | --- |
| Pick count matches what was requested | Reject with an exact-count retry instruction |
| Every pick is from a requested brand | Reject naming the off-brand picks |

Brand is already hard-filtered upstream, so this second check is defense in depth,
not the primary enforcement. It catches a regression in the filter rather than a model
mistake.

If both pass, the LLM judges two rubrics against real market numbers (retail, market
value, last sale, lowest ask, total sold):

1. **Value** — at least one pick should have market value above retail.
2. **Diversity** — picks should not all be the same brand.

The diversity rubric is *dropped entirely* when the shopper requested a specific
brand. Five Jordans in response to "show me Jordans" is exactly correct, and scoring
it as a diversity failure would fight the user's own request.

On rejection, the reason goes back into `sneaker_agent`'s prompt as feedback and it
tries again. After `MAX_CRITIQUE_ATTEMPTS = 2` cycles the picks are force-approved.
The shopper gets reviewed picks, not perfect ones, and never gets a hung request.

**8. Logistics agent reports.**
Queries live stock quantity per pick from the database — not the static `in_stock`
field in the JSON, which goes stale the moment anyone buys anything. Emits the report
in two shapes because two consumers need different things: `availability` as
structured rows for the web UI to render as a table, and `output` as aligned plain
text for the CLI and the eval report. Column widths are measured from the actual rows
so a long sneaker name does not break alignment.

Neither shape includes the raw StockX URL — it is long enough to swamp a line of text.
The UI turns the `link` field into a short labelled link instead.

If it receives no picks, it passes the upstream explanation through untouched rather
than overwriting it with "no sneakers to check". The shopper is better served by
"nothing matched under $80" than by a generic line.

---

## Flow 2 — Collection review

**Trigger:** *"What do I already own?"*

**Route:** `orchestrator → inventory_agent → END`

Collection resolution has three fallbacks in priority order:

1. `sneaker_collection` already in state (passed from the UI form)
2. Wardrobe rows from SQLite, looked up by username
3. `USER_SNEAKER_COLLECTION` dict in `data/catalog.py` (CLI and eval fallback)

The agent makes two model calls: one to summarize the collection and suggest an outfit
pairing or two, and a second to decide whether the request also implies shopping. If
it does, control passes to `sneaker_agent` and the shopping flow continues from there.

---

## Flow 3 — Compound request

**Trigger:** *"What do I already own, and what new heat should I cop?"*

**Route:** `orchestrator → inventory_agent → sneaker_agent → critique_agent → logistics_agent → END`

This is the case the deterministic router pre-check exists for. The regex catches the
"what do I already own" half, forces entry at `inventory_agent`, and `inventory_agent`'s
own shopping-intent check then hands off to `sneaker_agent` — so both halves of the
request get answered, in the right order. Full story in
[02-ai-ml-design.md](02-ai-ml-design.md#the-routing-bug-and-what-it-taught).

A false positive on that regex is harmless by design: a pure shopping request that
trips it still reaches `sneaker_agent`, just via one extra collection summary first.

---

## Flow 4 — Stock check

**Trigger:** *"Do you have the Jordan 4 Pine Green in stock?"*

**Route:** `orchestrator → logistics_agent → END`

No selection step and no model call inside the agent. Straight to the live stock
lookup.

---

## Flow 5 — Bidding

**Trigger:** Shopper names a price on one specific pair from the catalog page.

**Route:** Outside the graph entirely. `POST /api/bid → evaluate_bid()`

Bidding is not a routing decision — the sneaker is already chosen and the input is a
dollar amount. Running it as a graph node would add orchestration overhead to a
single-step evaluation.

Deterministic rejections run first, before any model call:

| Condition | Rejection |
| --- | --- |
| Not a real catalog item | "'X' is not a real catalog item." |
| Out of stock | "'X' is out of stock — there's nothing left to bid on." |
| Amount is zero, negative, or missing | "Bid must be a positive dollar amount." |

If the bid is structurally valid, the LLM compares it against retail price, market
value, lowest ask, and last sale, and returns ACCEPT or REJECT with reasoning in plain
English. An accepted bid immediately purchases: inventory decrements and the sneaker
lands in the bidder's wardrobe, the same mechanics as the flat-price Purchase button.

A race is handled explicitly — if the sneaker sells out between evaluation and
purchase, the API returns `409` with a message saying the bid was accepted but the
pair sold out. That is a live inventory race, not an evaluation failure, and the
shopper deserves to know the difference.

---

## Flow 6 — Purchase

**Trigger:** Purchase button on a sneaker card.

Decrements inventory by one and adds the sneaker to the buyer's wardrobe. Requires a
logged-in session, checked in the route handler rather than hidden in the UI, so a
direct API call is rejected the same way. Returns `409` if already out of stock.
Duplicate wardrobe entries are prevented by a unique constraint on
`(user_id, sneaker_name)`.

There is no balance check. Nothing is unaffordable.

---

## Flow 7 — Catalog browse

**Trigger:** The Catalog page, the app's default route.

`GET /api/sneakers` with five optional, combinable filters: free-text search across
name/brand/colorway, exact brand, silhouette, max retail price, and in-stock only.
This path is pure database and JSON — no agents, no model calls. Browsing should not
cost anything or take ten seconds.

---

## Flow 8 — Evals

**Trigger:** Evals page (admin session) or `python eval_runner.py`.

Runs 15 test cases through the real pipeline and scores each on the dimensions that
apply to it. Results stream case by case as they finish. Admins can also run a
free-text one-off scenario, which is scored only on the dimensions that do not need a
fixed expected outcome — latency, mainly. Full detail in
[05-evaluation.md](05-evaluation.md).

---

## Behavior rules that hold across every flow

These are the invariants. If any of them breaks, something is wrong.

1. **Every returned sneaker exists in the catalog.** Enforced by intersecting the
   model's answer with the pool it was shown.
2. **Every returned sneaker satisfies every hard constraint.** Enforced by filtering
   before selection, not by asking.
3. **Out-of-stock items are never recommended.** The stock filter runs first, against
   live database state.
4. **An unsatisfiable request gets a specific explanation, never a substitution.**
5. **The retry loop terminates.** Two cycles maximum, then force-approve.
6. **Deterministic checks precede LLM checks.** Facts do not need a model.
7. **Every request produces output.** Failure paths return readable messages; the eval
   harness scores this as its own dimension.
8. **Writes require a session.** Purchase and bid check auth in the route handler,
   before the model call, so an unauthenticated request never spends one.
