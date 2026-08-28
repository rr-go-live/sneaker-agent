# 04 — Data Schema

Every structure the system reads, writes, or puts on the wire.

---

## 1. Catalog (`data/sneakerdata.json`)

1,668 sneakers with real StockX market data, loaded into memory once at import time
as `SNEAKER_CATALOG` — a plain dict keyed by exact sneaker name.

```python
SNEAKER_CATALOG["Jordan 4 Retro SB Pine Green"]
```

Loading at import rather than per request is what makes catalog filtering cost
microseconds. The whole file is a few megabytes; a database round trip per filter pass
would dominate the agent's runtime for no benefit.

### Catalog entry

| Field | Type | Coverage | Meaning |
| --- | --- | --- | --- |
| *(key)* | string | 100% | Exact sneaker name. The primary key across the entire system. |
| `brand` | string | 100% | 23 distinct values. Hard-filter target. |
| `retail_price` | float | 100% | Original retail. **`0` means unknown, not free** — 10 entries. |
| `market_value` | float | 100% | Current resale value. |
| `lowest_ask` | float | 100% | Cheapest currently listed price. |
| `highest_bid` | float | 100% | Highest standing offer. |
| `last_sale` | float | 100% | Most recent sale price. |
| `deadstock_sold` | int | 100% | Lifetime units sold. |
| `sales_this_period` | int | 100% | Recent sales volume — the default popularity sort key. |
| `gender` | string | 100% | Men / Women / Grade School / Preschool / Toddler. |
| `profile` | string | 100% | `low` (1,340) / `high` (177) / `mid` (151). Hard-filter target. |
| `in_stock` | bool | 100% | Static flag, `true` for every entry. Superseded by live DB quantity. |
| `link` | string | 100% | StockX product URL. |
| `release_date` | string | 94.7% | ISO `YYYY-MM-DD`. **89 entries have none.** |
| `image` | string | 61.4% | Product photo URL, backfilled offline. |
| `colorway` | string | **0%** | Referenced in code, present in zero entries. |

Example:
```json
{
  "brand": "Jordan",
  "retail_price": 225.0,
  "market_value": 388.0,
  "gender": "Men",
  "profile": "low",
  "in_stock": true,
  "link": "https://stockx.com/jordan-4-retro-sb-pine-green",
  "lowest_ask": 325.0,
  "highest_bid": 480.0,
  "last_sale": 347.0,
  "release_date": "2023-03-21",
  "deadstock_sold": 5408,
  "sales_this_period": 2675,
  "image": "https://images.stockx.com/images/Air-Jordan-4-Retro-SB-Pine-Green-Product.jpg?..."
}
```

### Brand distribution

| Brand | Count | | Brand | Count |
| --- | --- | --- | --- | --- |
| Nike | 741 | | UGG | 11 |
| Jordan | 538 | | ASICS / Asics | 5 |
| adidas | 188 | | MSCHF | 2 |
| New Balance | 119 | | Alexander McQueen | 2 |
| Crocs | 18 | | OFF-WHITE | 2 |
| Converse | 15 | | Hoka One One | 2 |
| Puma | 14 | | The North Face | 2 |
| | | | Under Armour | 2 |

Plus single entries for Common Projects, Salomon, Birkenstock, Reebok, and others.

Two things this table explains. First, four brands cover 95% of the catalog, so a
brand hard-filter on anything else leaves a very small pool — which is why
`clamp_count_to_pool` exists and why "pick exactly 5" cannot be assumed satisfiable.
Second, the catalog holds both `ASICS` and `Asics` as separate brand strings, which is
why every brand comparison in the codebase is case-insensitive and why
`extract_requested_brands` deduplicates case-insensitively while keeping the catalog's
own spelling.

### Data quality notes that drive real behavior

**`colorway` is absent from every entry.** The field is read in three places —
`filter_by_color`, the prompt's catalog lines, and the `/api/sneakers` search target —
and it resolves to empty every time. Color matching therefore happens entirely against
the sneaker *name*, which works because names encode colorways by convention
("Nike Dunk Low Retro White Black Panda"). This is precisely why color is a soft
preference with a documented fallback rather than a hard filter: a hard filter on a
field with zero coverage would return nothing for every color request.

**`retail_price: 0` means unknown.** Ten entries. Treated as unknown consistently:
excluded when a price ceiling is set, and sorted last in *both* price orderings — not
just descending. Sorting them naively would answer "what's your cheapest sneaker?"
with a shoe nobody has a price for.

**89 entries have no `release_date`.** Excluded when a release-year floor is set, on
the same principle: an unknown date cannot be confirmed to satisfy "released after
2022", and including it would present an unverified item as a match.

**`in_stock` is `true` for all 1,668 entries and is effectively dead data.** Live
availability lives in the `sneaker_inventory` table. The agents query that; only
`GET /api/sneakers` still reads the static flag, which is the source of the
browse/recommend disagreement noted in [03-api-and-services.md](03-api-and-services.md#known-gaps).

**`image` covers 61.4%.** Cards fall back to a colorway-derived color swatch when
absent. Backfill is offline and resumable via `backfill_images.py`, which prioritizes
by `sales_this_period` and marks permanent no-matches so they are never re-queried —
the free KicksDB tier allows 1,000 requests a month against a 1,668-entry catalog, so
the script is built to pick up where it left off next billing cycle at no extra cost.

---

## 2. Database (`sneaker_agent.db`, SQLite via SQLAlchemy 2.0)

Three tables. Models are in [database.py](../database.py).

### `users`

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | Integer | PK, autoincrement |
| `username` | String(64) | Unique, not null, indexed |
| `password_hash` | String(128) | Nullable — `salt_hex$hash_hex`, PBKDF2-HMAC-SHA256 |
| `is_admin` | Boolean | Not null, default `false` |
| `created_at` | DateTime | Defaults to now |

`password_hash` is nullable because rows created before login existed have none.
`verify_login` treats a null hash as a failed login rather than as a passwordless
account — an important distinction, since the alternative is an open door.

Relationship: `wardrobe` → `WardrobeItem`, `cascade="all, delete-orphan"`, ordered by
`added_at`. Deleting a user removes their wardrobe rather than orphaning them.

### `wardrobe_items`

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | Integer | PK, autoincrement |
| `user_id` | Integer | FK → `users.id`, not null |
| `sneaker_name` | String(256) | Not null — must match a `SNEAKER_CATALOG` key exactly |
| `added_at` | DateTime | Defaults to now |

Unique constraint on `(user_id, sneaker_name)` — `uq_user_sneaker`. Owning two of the
same pair is not modeled, and enforcing that in the schema means the application layer
does not have to remember to check.

`sneaker_name` is a string reference into a JSON file, not a foreign key. That is a
real trade-off: it keeps the catalog swappable without a migration, and it means a
renamed catalog entry silently orphans wardrobe rows. `db_init.py` carries a
`WARDROBE_NAME_FIXES` map that repairs known drift on every run, applied to existing
databases and not just fresh ones — which is the cost of this choice, made visible.

### `sneaker_inventory`

| Column | Type | Constraints |
| --- | --- | --- |
| `sneaker_name` | String(256) | **PK** — matches `SNEAKER_CATALOG` keys |
| `quantity` | Integer | Not null, default 1 |
| `updated_at` | DateTime | Auto-updated on write |

Seeded with one row per catalog entry at quantity 1. `purchase_sneaker` decrements and
refuses to go below zero. `get_out_of_stock_names()` returns the set with
`quantity <= 0`, which `sneaker_agent` uses to exclude sold-out items before
filtering anything else.

`quantity` starting at 1 makes stock scarcity real in a demo: buying a sneaker removes
it from everyone's recommendations immediately, which exercises the out-of-stock paths
that would otherwise never fire.

### Migration approach

`init_db()` runs `create_all` then `_add_missing_columns()`, a small SQLite-specific
routine that adds columns present on the model but missing from an existing table.
`create_all` only creates missing tables — it never alters an existing one, so adding
`password_hash` and `is_admin` to a live dev database would otherwise require deleting
it.

This is not a migration framework and is not pretending to be one. It handles additive
column changes so local databases survive upgrades. Production needs Alembic — renames,
drops, type changes, and data migrations are all outside what this handles.

---

## 3. Agent state (`AgentState`, [state.py](../state.py))

A `TypedDict` that travels through the entire graph. Every agent reads what it needs
and returns only the fields it changed; LangGraph merges that dict back in.

| Field | Type | Written by | Purpose |
| --- | --- | --- | --- |
| `input` | str | caller | Original user request |
| `user_name` | str | caller | Whose wardrobe to look up |
| `next` | str | every agent | Node the router sends control to |
| `output` | str | every agent | Human-readable result of the last agent |
| `proposed_sneakers` | list[str] | `sneaker_agent` | Selected catalog names |
| `sneaker_collection` | list[str] | `inventory_agent` | What the user owns |
| `critique_feedback` | str \| None | `critique_agent` | Rejection reason, injected into the retry prompt |
| `critique_attempts` | int | `critique_agent` | Cycle counter, capped at 2 |
| `reasoning` | str \| None | every agent | Plain-English explanation, streamed to the UI |
| `requested_brands` | list[str] | caller or `sneaker_agent` | Brand filter — resolved value written back |
| `requested_colors` | list[str] | caller or `sneaker_agent` | Color filter — resolved value written back |
| `requested_profile` | str \| None | caller or `sneaker_agent` | `low` / `mid` / `high` |
| `requested_count` | int \| None | `sneaker_agent` | Pick count after clamping |
| `availability` | list[dict] \| None | `logistics_agent` | Structured stock rows for the UI table |
| `retail_total` | float \| None | `logistics_agent` | Summed retail of the picks |
| `no_matches` | bool \| None | `sneaker_agent` | Nothing satisfied the constraints — skip the retry loop |

Three details in this table are load-bearing:

**`requested_brands` is written back after resolution.** A brand parsed out of free
text never appears in the incoming structured field. Writing the resolved value back
into state is what lets `critique_agent` enforce the same brand rule `sneaker_agent`
filtered on. Without it the critic would check against an empty list and pass anything.

**Price ceiling and release year are *not* in state.** They are parsed per request
inside `sneaker_agent` and deliberately not carried, because nothing downstream needs
to re-check them — the candidate pool physically cannot contain a violation. State
carries what other agents need, not everything that was computed.

**`no_matches` exists to suppress a retry, not to report a result.** It is a control
signal between two agents.

### `availability` row

Built by `logistics_agent`, rendered as a table by the UI:

```json
{
  "name": "Jordan 4 Retro SB Pine Green",
  "brand": "Jordan",
  "in_stock": true,
  "quantity": 1,
  "retail": 225.0,
  "market": 388.0,
  "link": "https://stockx.com/...",
  "found": true
}
```

`found: false` means the name was not in the catalog — every other field is then
null or zero. It is a distinct state from "in the catalog but out of stock", and the
UI shows them differently.

---

## 4. Wire payloads

### Agent SSE events

**`agent_step`** — one per completed node:
```json
{
  "type": "agent_step",
  "node": "sneaker_agent",
  "label": "Sneaker Advisor",
  "summary": "Selected: Jordan 4 Retro, Nike Dunk Low...",
  "reasoning": "Both lean toward the low-top, neutral look the user asked for.",
  "next": "critique_agent"
}
```

`node` is the internal name, `label` is the display name from `NODE_LABELS`, `summary`
is a one-line description built per node type by `_node_summary`, `reasoning` is the
model's own explanation. `next` is nulled when it is not a displayable node — `END`
never reaches the client as a step target.

**`result`** — once, after the graph finishes:
```json
{
  "type": "result",
  "sneakers": [ { "name": "...", "quantity": 1, "in_stock": true, "...": "full catalog fields" } ],
  "output": "Sneaker Availability Report:\n\n  ..."
}
```

`quantity` and `in_stock` are re-queried live at this point rather than reusing what
`logistics_agent` saw, so a card cannot render "in stock" for something bought
mid-request.

**`error`** — `{"type": "error", "message": "..."}`

Every stream terminates with `data: [DONE]`, success or failure.

### Eval SSE events

**`eval_case`** — one per finished test case:
```json
{
  "type": "eval_case",
  "id": "TC-001", "name": "Direct shopping request",
  "description": "...", "input": "...", "user_name": "john",
  "passed": true, "overall_score": 1.0, "total_latency": 12.4,
  "nodes_visited": ["orchestrator", "sneaker_agent", "critique_agent", "logistics_agent"],
  "node_latencies": {"orchestrator": 0.9, "sneaker_agent": 8.2, "...": 0},
  "scores": { "routing": {"passed": true, "score": 1.0, "reason": "routed to 'sneaker_agent' ✓"} },
  "output": "...", "availability": [], "retail_total": 1105.0, "error": null
}
```

**`eval_summary`** — once at the end:
```json
{
  "type": "eval_summary",
  "total": 15, "passed": 15, "avg_score": 0.93, "total_time": 161.8,
  "dimension_scores": { "routing": {"avg": 1.0, "pass_count": 11, "total": 11} }
}
```

`passed` on a case means no exception *and* every applicable scorer passed.
`overall_score` is the mean of applicable scorer scores, so a case can score 83% while
still passing if a scorer awards partial credit without failing.

---

## 5. Eval structures

### Test case (`evals/cases.py`)

| Field | Type | Purpose |
| --- | --- | --- |
| `id` | str | `TC-001` … `TC-015` |
| `name` | str | Short label |
| `description` | str | What this case is testing and why |
| `kind` | str | `graph` (default) or `bid` |
| `input` | str | The request text |
| `user_name` | str | Whose wardrobe context to use |
| `expected_first_agent` | str \| None | Routing target — `None` skips routing scoring |
| `expect_proposed_sneakers` | bool | Should picks be produced? |
| `expected_pick_included` | str \| None | A specific catalog name that must appear |
| `expected_constraints` | dict \| None | `brands`, `profile`, `max_price`, `min_year` |
| `is_failure_case` | bool | Does this intentionally hit an error path? |
| `expected_output_contains` | str \| None | Substring the output must include |
| `sneaker_name` | str | Bid cases only |
| `bid_amount` | float | Bid cases only |
| `expected_accepted` | bool \| None | Bid cases only |

Every expectation field is optional, and `None` means *skip that dimension for this
case* rather than *expect nothing*. That is what lets one scorer set cover fifteen
structurally different cases without branching.

### `RunResult`

```python
{
  "test_case":      dict,           # the case that produced this
  "final_state":    dict,           # all node updates merged
  "nodes_visited":  list[str],      # execution order, retries included
  "node_outputs":   dict,           # {node: state_updates}
  "node_latencies": dict,           # {node: seconds}
  "total_latency":  float,
  "agent_logs":     str,            # captured stdout, empty when verbose
  "scores":         dict,           # {scorer_name: ScoreResult}
  "overall_score":  float,          # 0.0–1.0
  "error":          str | None,     # exception message if one escaped
}
```

Bid cases produce the same shape — `nodes_visited` is `["bid_agent"]` and
`final_state` is synthesized from the `{accepted, reasoning}` dict. Converging both
kinds on one structure is why scorers and the report never branch on case type.

### `ScoreResult`

```python
{ "passed": bool, "score": float, "reason": str }
```

Or `None`, meaning the scorer does not apply and is excluded from that case's average.

---

## 6. Migrating to Postgres

The models port by changing `DATABASE_URL`. What does not port for free:

| Concern | SQLite today | Postgres |
| --- | --- | --- |
| Concurrency | File-level write serialization makes read-then-write safe by accident | Needs `SELECT ... FOR UPDATE` or an atomic conditional update on `purchase_sneaker` |
| Connections | `check_same_thread=False`, one shared engine | Connection pool sized to worker count |
| Schema changes | `_add_missing_columns()` bolt-on | Alembic |
| `DateTime` defaults | Python-side `datetime.utcnow` | Consider `server_default=func.now()` for clock consistency |
| Catalog | JSON in memory | Stays in memory, or becomes a table with indexes on brand/profile/retail/release_date |

The catalog question is the interesting one. In memory, filtering 1,668 rows is
microseconds and cost-free. Past roughly 50,000 entries, or once catalog data needs to
change without a deploy, it becomes a table with a composite index on the hard-filter
columns. The filtering functions in `selection.py` are already written as pure
transformations over `(name, details)` pairs, so swapping the source behind them
touches one layer.

---

## Business impact, if this shipped

**Schema-level constraints eliminate whole bug classes.** The unique constraint on
`(user_id, sneaker_name)` means duplicate wardrobe entries cannot exist regardless of
what the application layer forgets to check. The cascade delete means user removal
cannot orphan rows. Constraints in the schema are enforced once; constraints in
application code are enforced everywhere you remember.

**Documented data-quality gaps prevent silent wrong answers.** Zero colorway coverage
and ten unknown retail prices are not edge cases — they are conditions the code
handles explicitly and visibly. The alternative is a system that returns a $0 sneaker
as "cheapest" and a color match that was never verified, both with full confidence.
In retail those become returns, chargebacks, and support tickets.

**Live inventory as a real transactional concept is what makes recommendations
trustworthy.** Recommending a sold-out item is a guaranteed dead end for a shopper who
has already decided to buy. Querying live quantity instead of a static flag, and doing
it as the *first* filter, means recommendations are actionable by construction.

**The string reference from wardrobe to catalog is a documented trade-off, not an
oversight.** It keeps the catalog swappable without a migration and costs a name-drift
repair map. Writing that cost down — including the fix that runs on every seed — is
what stops it becoming a mystery six months later when someone finds wardrobe rows
that match nothing.

**One `RunResult` shape across two execution paths is why the eval harness stays
maintainable.** Graph runs and bid runs share nothing operationally, but they converge
on one structure, so scorers and reporting have no idea which produced them. Adding a
third execution kind means writing one runner, not editing seven scorers.
