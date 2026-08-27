# Test Cases — Sneaker Agent

This project has two complementary test layers:

1. **CLI test harness** ([`cli_test.py`](cli_test.py)) — fast structural and
   integration checks (parser, API routes, database, selection logic, bid
   validation/fairness, and one full pipeline run). Run it with
   `python cli_test.py`. See [CLI Test Harness](#cli-test-harness-cli_testpy)
   below.
2. **Eval harness** — quality scoring across realistic prompts, covering both
   the multi-agent graph (routing, picks) and the standalone bid_agent
   (fairness). Run the full suite with `python eval_runner.py` or a single
   case with `python eval_runner.py --id TC-001`.

---

## Scoring Dimensions

There is no budget concept in this app — sneaker_agent has no price ceiling,
so there's no "budget accuracy" or "budget compliance" dimension.

The eval harness runs two kinds of test cases (see `kind` in
[evals/cases.py](evals/cases.py)): `"graph"` (default) streams the full
LangGraph pipeline; `"bid"` calls `bid_agent.evaluate_bid()` directly, since
bidding targets one already-known sneaker rather than a routing decision.
Both kinds are scored and reported the same way.

| Dimension | What it checks | Applies to |
|---|---|---|
| Routing Accuracy | Did the orchestrator pick the correct first agent? | graph cases |
| Sneaker Validity | Are all proposed sneakers real catalog items (no hallucination)? | graph cases with `expect_proposed_sneakers` |
| Expected Pick | Does one specific catalog name actually appear in the picks? Stronger than Sneaker Validity — validity only rules out hallucination, this checks the *right* answer was found. | graph cases with `expected_pick_included` |
| Constraint Fidelity | Does **every** pick satisfy the brand, silhouette, price ceiling and release year the user stated? The end-to-end guard on free-text constraint extraction. | graph cases with `expected_constraints` |
| Bid Fairness | Does bid_agent accept/reject in line with real market data? | bid cases with `expected_accepted` |
| Failure Handling | Does the system return a graceful error message instead of crashing? | cases with `is_failure_case: True` |
| Latency | Did the full run finish within the acceptable time window (< 15s pass, < 30s warn)? | all |

---

## Test Cases

### TC-001 — Direct Shopping Request
| Field | Value |
|---|---|
| Input | "Help me find some fresh kicks to add to my collection" |
| User | John |
| Expected chain | orchestrator → sneaker_agent → critique_agent → logistics_agent |
| Expected first agent | sneaker_agent |
| Expect proposed sneakers | Yes |

**What it validates:** The most common happy path. Shopping intent must route directly to sneaker_agent, and all proposed names must be real catalog entries.

---

### TC-002 — Collection Check Only (No Shopping)
| Field | Value |
|---|---|
| Input | "What sneakers do I already have in my collection?" |
| User | Alice |
| Expected chain | orchestrator → inventory_agent → END |
| Expected first agent | inventory_agent |
| Expect proposed sneakers | No |

**What it validates:** Pure collection-review intent should stop at inventory_agent. No sneaker_agent run expected. Tests the LLM-based routing decision inside inventory_agent.

**Edge cases:** If inventory_agent's internal LLM misreads the intent as "shop", sneaker_agent will run unexpectedly. This is a known flakiness risk.

---

### TC-003 — Inventory Review Then Shopping
| Field | Value |
|---|---|
| Input | "I want to upgrade my sneaker collection. What do I already own, and what new heat can I cop to complete the rotation?" |
| User | John |
| Expected chain | orchestrator → inventory_agent → sneaker_agent → critique_agent → logistics_agent |
| Expected first agent | inventory_agent |
| Expect proposed sneakers | Yes |

**What it validates:** The most complex routing path. The request contains both "see collection" and "buy new" intent. inventory_agent must run first.

**Formerly a real, non-flaky bug:** the LLM-based orchestrator routed this to sneaker_agent 5/5 runs, skipping inventory_agent entirely — its prompt calls sneaker_agent "the default for anything sneaker-related," which biased it away from inventory_agent whenever shopping language was present at all. **Fixed** with a deterministic pre-check, `orchestrator._mentions_existing_collection` — collection-referencing language now routes straight to inventory_agent without an LLM call at all, so this case is no longer subject to LLM judgment. See [section 12](#12-orchestrator-collection-routing-orchestrator_mentions_existing_collection) below.

---

### TC-004 — Style Advice Request
| Field | Value |
|---|---|
| Input | "What are the hottest sneaker styles and trends right now?" |
| User | John |
| Expected chain | orchestrator → sneaker_agent → critique_agent → logistics_agent |
| Expected first agent | sneaker_agent |
| Expect proposed sneakers | Yes |

**What it validates:** A trend/style question routes the same way as a direct buying request — sneaker_agent always proposes picks now, regardless of how the intent is framed.

---

### TC-005 — Stock Availability Check
| Field | Value |
|---|---|
| Input | "Is the Jordan 4 Retro Infrared available in the store right now?" |
| User | John |
| Expected chain | orchestrator → logistics_agent |
| Expected first agent | logistics_agent |
| Expect proposed sneakers | No |

**What it validates:** Asking about a specific named sneaker's stock status should go straight to logistics_agent without running any other agent. Note: logistics_agent reports "No sneakers to check" because it reads from `proposed_sneakers` (set by sneaker_agent), which is empty on a direct route. This is a known gap in the current implementation.

---

### TC-006 — Alice Shopping Request
| Field | Value |
|---|---|
| Input | "I want to buy some new heat for my collection" |
| User | Alice |
| Expected chain | orchestrator → sneaker_agent → critique_agent → logistics_agent |
| Expected first agent | sneaker_agent |
| Expect proposed sneakers | Yes |

**What it validates:** Confirms shopping-intent routing holds for a second user, not just John.

---

### TC-007 — Minimal One-Word Query (No Crash)
| Field | Value |
|---|---|
| Input | "sneakers" |
| User | John |
| Expected chain | any valid route |
| Expected first agent | (not checked) |
| Is failure case | No |

**What it validates:** The system should handle extremely vague input without crashing. Routing is not checked — only that the system produces some output and does not raise an exception. This is a robustness smoke test.

---

### TC-008 — Lowball Bid Rejected
| Field | Value |
|---|---|
| Kind | bid |
| Input | Bid $50.00 on Jordan 4 Retro SB Pine Green (retail $225, market $388, lowest ask $325) |
| Expected outcome | Rejected |

**What it validates:** `bid_agent`'s fairness judgment actually discriminates on real pricing data — a bid far below every reference price is not fair to the seller.

---

### TC-009 — Fair Bid Accepted
| Field | Value |
|---|---|
| Kind | bid |
| Input | Bid $320.00 on Jordan 4 Retro SB Pine Green (same sneaker as TC-008) |
| Expected outcome | Accepted |

**What it validates:** A bid close to the lowest ask is accepted, proving the judgment isn't just rejecting everything. Both this and TC-008 restock the sneaker to quantity 1 before running (via `database.restock_sneaker`) so the result never depends on whatever a prior manual purchase left the live dev database at.

---

### TC-010 — Bid on Unknown Sneaker Rejected
| Field | Value |
|---|---|
| Kind | bid |
| Input | Bid $500.00 on "Definitely Not A Real Sneaker XYZ" |
| Expected outcome | Rejected, deterministically — no LLM call |
| Is failure case | Yes — `expected_output_contains: "not a real catalog item"` |

**What it validates:** `validate_bid_request` catches an invalid target before any market judgment is attempted.

---

### TC-011 — Highest Retail Jordans Post-2022
| Field | Value |
|---|---|
| Input | "Get me the single highest retail value Jordan released after 2022" |
| Expected first agent | sneaker_agent |
| Expected pick included | "Jordan 1 Low SE True Blue" |
| Expected constraints | brand Jordan, released 2022 or later |

**What it validates:** a superlative combined with a date filter. Previously a
documented known-limitation case: with no release-year filter and no
retail-price sort, candidates were ranked by popularity and capped at
`MAX_CATALOG_SIZE` (80), so the correct answer — "Jordan 1 Low SE True Blue"
($1,110 retail, released 2022-06-22), ranked **#197 of 538** in-stock Jordans
by popularity — never reached the LLM at all. `extract_min_release_year` +
`extract_sort_preference` + `sort_candidates` closed that gap. Ordering must
happen *before* the cap, which is the whole point of this case.

---

### TC-012 — Free-Text Brand + Silhouette + Budget
| Field | Value |
|---|---|
| Input | "get me a low top jordan sneaker that I can get with 150 dollars" |
| Expected constraints | brand Jordan, low profile, retail ≤ $150 |

**What it validates:** the exact query that surfaced this whole class of bug.
The admin Custom Scenario panel sends only a raw string with no structured
filter fields, so brand, silhouette and price all have to be parsed from
prose. Before `extract_requested_brands` existed, this returned Nike and
adidas picks for a query that plainly said "jordan" — and the prompt actively
told the LLM to "favor variety across brands", steering it further away.

---

### TC-013 — Cheapest New Balance
| Field | Value |
|---|---|
| Input | "what is the cheapest New Balance you have" |
| Expected constraints | brand New Balance |

**What it validates:** the opposite sort direction from TC-011, plus a
multi-word brand matched as a phrase.

---

### TC-014 — Colorway + Brand + Budget Stack
| Field | Value |
|---|---|
| Input | "I want black Nike low tops under 120 dollars" |
| Expected constraints | brand Nike, low profile, retail ≤ $120 |

**What it validates:** several constraints stacked in one sentence — the way
a real shopper actually types — all surviving to the final picks.

---

### TC-015 — Impossible Budget Fails Honestly
| Field | Value |
|---|---|
| Input | "find me a jordan under 10 dollars" |
| Expect proposed sneakers | No |
| Is failure case | Yes — `expected_output_contains: "No in-stock sneakers matched"` |

**What it validates:** a constraint nothing in the catalog satisfies must
produce an honest, specific empty result naming which filters failed — never
a silent substitution of off-brand or over-budget picks. This case caught
three real bugs on its first run:

1. `filter_by_max_price` treated `retail_price: 0.0` (10 catalog entries,
   meaning *unknown*) as satisfying any ceiling, so a $0 shoe passed an
   "under $10" filter.
2. `logistics_agent` overwrote sneaker_agent's specific explanation with a
   generic "No sneakers to check availability for."
3. `critique_agent` spun its full retry loop on an unsatisfiable request and
   then force-approved with "Picks approved after review.", replacing the
   explanation entirely. It now short-circuits on the `no_matches` flag,
   which also cut this case's runtime from 7.7s to 1.1s.

---

## Running Results Interpretation

- **All dimensions 100%** — pipeline is healthy
- **Routing Accuracy drops** — check `orchestrator._mentions_existing_collection` first if the miss involves collection language; otherwise the LLM routing prompt needs tuning for the query type that misrouted
- **Sneaker Validity drops** — LLM is hallucinating catalog names; the catalog-validation logic in sneaker_agent may need strengthening
- **Constraint Fidelity drops** — free-text extraction in `agents/selection.py` missed a constraint, or a filter regressed; check which constraint the failing pick violated (the reason string names it)
- **Bid Fairness drops** — bid_agent's LLM judgment is misreading market data, or `validate_bid_request`'s deterministic checks regressed
- **Failure Handling shows n/a** — expected when no test case in the current run sets `is_failure_case: True`
- **Latency drops** — LLM API is slow; check model tier or reduce prompt length

---

# CLI Test Harness (`cli_test.py`)

Fast, mostly-offline checks that confirm the app's building blocks work.
Run with `python cli_test.py`. Exits `0` when everything passes or is
skipped, `1` on any failure (CI-friendly). Cases that make live Gemini
calls are skipped automatically when no `GOOGLE_API_KEY` is configured, and
a dummy key is injected so the offline cases can still import the API.

## 1. Reasoning parser (`reasoning.split_reasoning_answer`)

The LLM agents return their thinking and their machine-readable answer in a
single `REASONING: … / ANSWER: …` response. The parser splits the two.

| # | Input | Expected output | Edge case covered |
|---|-------|-----------------|-------------------|
| 1.1 | `"REASONING: because.\nANSWER: financial_agent"` | `("because.", "financial_agent")` | Well-formed, multi-line |
| 1.2 | `"ANSWER: sneaker_agent"` | `("", "sneaker_agent")` | Reasoning label omitted |
| 1.3 | `"financial_agent"` | `("", "financial_agent")` | No labels — backwards-compatible fallback so routing never breaks |
| 1.4 | `"reasoning: lower\nanswer: done"` | `("lower", "done")` | Lowercase labels |
| 1.5 | `""` | `("", "")` | Empty / null input does not raise |

## 2. Catalog filter endpoint (`GET /api/sneakers`)

| # | Input | Expected output | Edge case covered |
|---|-------|-----------------|-------------------|
| 2.1 | `?q=panda` | HTTP 200, JSON list | Query touches entries with **no `colorway` key** — previously threw `KeyError` (500) |
| 2.2 | `?q=panda` (rows present) | Each row contains a `name` field | Response shape is stable for the frontend |
| 2.3 | `?max_price=120` | HTTP 200, every row `retail_price <= 120` | Numeric filter correctness |

Related safety handled in `api.py`: entries missing `brand`, `retail_price`,
or `in_stock` are treated as empty/absent instead of crashing the request.

## 3. User profile routes (`/api/users`)

| # | Input | Expected output | Edge case covered |
|---|-------|-----------------|-------------------|
| 3.1 | `GET /api/users` | HTTP 200, JSON list | Works whether or not users are seeded |
| 3.2 | `GET /api/users/definitely-not-a-real-user-xyz` | HTTP 404 | Unknown username rejected cleanly |
| 3.3 | `GET /api/users/{seeded}` | HTTP 200, `wardrobe` is a list | Known user returns a wardrobe (skipped if none seeded) |

## 4. Database helpers (`database.py`)

| # | Input | Expected output | Edge case covered |
|---|-------|-----------------|-------------------|
| 4.1 | `init_db()` | No error | Idempotent — safe when tables already exist |
| 4.2 | `get_sneaker_quantity(name)` | Non-negative `int` | Valid count for known/unknown sneaker |
| 4.3 | `get_out_of_stock_names()` | Python `set` | Stable return type for downstream filtering |

## 5. Selection logic (`agents/selection.py`)

Pure-function tests for the deterministic filtering/validation logic
sneaker_agent relies on instead of soft prompt wording. No LLM or database
calls — fast and fully deterministic.

| # | Function | Case | Edge case covered |
|---|----------|------|--------------------|
| 5.1 | `filter_by_brand` | no brands requested | returns candidates unchanged |
| 5.2 | `filter_by_brand` | `["Jordan"]` | filters to only that brand, case-insensitive |
| 5.3 | `filter_by_brand` | brand with zero matches | returns `[]` — never silently substitutes another brand |
| 5.4 | `filter_by_color` | no colors requested | returns candidates unchanged |
| 5.5 | `filter_by_color` | `["Grey"]` | matches on colorway substring |
| 5.6 | `filter_by_color` | color with zero matches | falls back to the full pool, reports `matched=False` |
| 5.7 | `extract_requested_count` | no number mentioned | falls back to the default (5) |
| 5.8 | `extract_requested_count` | "released after 2020" | a year is never mistaken for a count |
| 5.9 | `extract_requested_count` | "give me just 2 options" / "show me three pairs" | parses explicit digit and number-word counts |
| 5.10 | `extract_requested_count` | "I want 20 sneakers" | clamps to the max (10) |
| 5.11 | `extract_proposed_names` | LLM mentions a name outside its shown candidate pool | ignored — guards against hallucinated picks bypassing brand/stock filtering |
| 5.12 | `clamp_count_to_pool` | requesting 5 from a pool of 2 | reduces to what the pool can actually supply |

## 6. Full multi-agent pipeline (`graph.build_graph`)

Runs a complete buying request through the graph
(orchestrator → sneaker_agent → critique_agent → logistics_agent). There is
no budget in this app, so there's nothing to check picks against on that
front — any in-stock sneaker is a valid candidate.

**Input:**
```python
{
  "input": "I want a clean white low-top for everyday wear that holds resale value",
  "user_name": "cli_test_user",
}
```

| # | Expected output | Edge case covered |
|---|-----------------|-------------------|
| 6.1 | Visits `orchestrator` and `sneaker_agent` | Routing works for shopping intent |
| 6.2 | **Every** node emits non-empty `reasoning` | Powers the Reasoning tab's step-by-step LLM reasoning |
| 6.3 | `proposed_sneakers` has ≥ 1 pick | Sneaker agent produces output |

**Skip condition:** reported `SKIP` when no real `GOOGLE_API_KEY` is set,
since it makes live Gemini calls. The harness still exits successfully.

## 7. Brand/count compliance (regression for a reported bug)

Live regression test for a real bug: a Jordan brand filter plus a Grey
colorway filter, with no explicit count, was returning an off-brand
(Adidas) pick in the wrong color and only 2 results instead of the
intended default of 5.

**Input:** brand filter `["Jordan"]`, color filter `["Grey"]`, free text
mentioning both preferences, no explicit count.

| # | Expected output | Edge case covered |
|---|-----------------|--------------------|
| 7.1 | Every proposed pick's brand is Jordan | Hard brand filter actually holds end-to-end against a live LLM |
| 7.2 | Proposed count matches what `clamp_count_to_pool(5, pool_size)` computes independently | Default count of 5 is honored, not silently truncated |

**Skip condition:** same as above — `SKIP` without a real `GOOGLE_API_KEY`.

## 8. Bid agent (`agents/bid_agent.py`)

Bidding targets one already-known sneaker and runs standalone, outside the
LangGraph pipeline — `api.py` calls `bid_agent.evaluate_bid()` directly.

**8a. Deterministic pre-checks (`validate_bid_request`)** — no LLM or
database calls, fast and fully deterministic:

| # | Case | Expected output |
|---|------|-----------------|
| 8.1 | Sneaker not in the catalog | Rejected, with a reason |
| 8.2 | Sneaker in the catalog but out of stock | Rejected, with a reason |
| 8.3 | Bid amount is zero or negative | Rejected, with a reason |
| 8.4 | Real, in-stock sneaker with a positive bid | Passes validation |

**8b. Fairness judgment (`evaluate_bid`, live LLM)** — restocks "Jordan 4
Retro SB Pine Green" to quantity 1 first (via `database.restock_sneaker`) so
the result never depends on whatever a prior manual purchase left the live
dev database at. Real data for this sneaker: retail $225, market $388,
lowest ask $325.

| # | Bid | Expected outcome |
|---|-----|-------------------|
| 8.5 | $50.00 | Rejected — far below retail/market/lowest-ask |
| 8.6 | $320.00 | Accepted — close to the lowest ask |

**Skip condition:** 8b is `SKIP` without a real `GOOGLE_API_KEY`, since it
makes live Gemini calls. 8a always runs.

## 9. Query understanding (`agents/selection.py` extractors)

Parses brand, color, silhouette, price ceiling, release year and sort
preference out of free text. A constraint reaches the agent either as a
structured field from the Advisor UI's filter chips, or named in prose from
the free-text box, the admin Custom Scenario panel, or the CLI. Only the
structured path used to be honored.

No LLM or database calls — fast and fully deterministic.

| # | Case | Expected | Edge case covered |
|---|------|----------|--------------------|
| 9.1 | "get me a low top jordan" | brand Jordan | brand named in prose |
| 9.2 | "3 pairs of grey jordans" | brand Jordan | plural brand mention |
| 9.3 | "jordan's are my favorite" | brand Jordan | possessive brand mention |
| 9.4 | "the cheapest new balance" | brand New Balance | multi-word brand matched as a phrase |
| 9.5 | "no jordans please" | no brand | negation must not invert into a filter |
| 9.6 | "anything but adidas" | no brand | exclusion phrasing |
| 9.7 | "I already own nikes" | no brand | owning a brand is not a request for it |
| 9.8 | "red and black colorway" | black + red | multiple colors in one request |
| 9.9 | "low tops" / "high-top" | low / high | plain and hyphenated silhouettes |
| 9.10 | 7 budget phrasings | correct ceiling | "with 150 dollars", "under 100", "nothing over $200", "300 dollars max", "I have 250 bucks", "budget of 300", "$180 or less" |
| 9.11 | "sneakers with 3 stripes" | no budget | a bare number with no currency marker must not parse as $3 |
| 9.12 | "size 10 low tops" | no budget | a shoe size is not a budget |
| 9.13 | "released after 2022" / "from 2023 onwards" | 2022 / 2023 | release-year floor |
| 9.14 | "most expensive" / "highest retail value" | retail_desc | superlative re-ranks the pool |
| 9.15 | "cheapest" | retail_asc | opposite direction |
| 9.16 | "300 dollars max" | no sort | a price ceiling is not a request for the priciest shoe |

## 10. Constraint filters (`agents/selection.py` filters + ordering)

Applies the extracted constraints to the candidate pool. The ordering tests
matter more than they look: the pool is capped at `MAX_CATALOG_SIZE` before
the LLM sees it, so an unsorted superlative query's correct answer can sit
outside the window and never reach the model.

| # | Function | Case | Edge case covered |
|---|----------|------|--------------------|
| 10.1 | `filter_by_profile` | zero matches | returns empty, never a different silhouette |
| 10.2 | `filter_by_max_price` | ceiling is inclusive | `<=`, not `<` |
| 10.3 | `filter_by_max_price` | `retail_price: 0.0` | 0 means *unknown*, not free — must not satisfy an arbitrary ceiling (10 real catalog entries have this) |
| 10.4 | `filter_by_release_year` | entry with no `release_date` | excluded — an unknown date can't be confirmed to match |
| 10.5 | `sort_candidates` | retail_desc / retail_asc | highest / lowest retail first |
| 10.6 | `sort_candidates` | unknown price under retail_asc | sorts last, so "the cheapest" is never a shoe whose price nobody knows |
| 10.7 | `sort_candidates` | default | popularity (`sales_this_period`) |
| 10.8 | `sort_candidates` | — | does not mutate the caller's list |

## 11. Availability report (`agents/logistics_agent.py`)

`logistics_agent` emits its report in two shapes, because two consumers need
it differently: structured rows (`availability`) that the web dashboard
renders as a table, and an aligned plain-text version (`output`) for the CLI
and eval report, which have no table to render into. Neither includes the
raw StockX URL — it is long enough to dominate a line and adds nothing the
sneaker name doesn't already convey. The UI turns the `link` field into a
short "StockX ↗" link instead.

Tests target `_format_report_text`, a pure function — no LLM or database calls.

| # | Case | Expected |
|---|------|----------|
| 11.1 | Any report | contains no `stockx.com` URL |
| 11.2 | In-stock and out-of-stock rows | each row shows its live status |
| 11.3 | Sneaker absent from the catalog | reported explicitly, not silently dropped |
| 11.4 | Any report | includes the estimated retail total |
| 11.5 | Names of differing length | columns still align (measured by the retail column offset) |
| 11.6 | Empty row list | readable message, not an empty report |

## 12. Orchestrator collection routing (`orchestrator._mentions_existing_collection`)

Regression test for a real, non-flaky bug: the orchestrator's LLM routing
call sent a compound request — referencing the existing collection AND
asking for new picks — to `sneaker_agent` 5/5 times, skipping
`inventory_agent` entirely (see TC-003, and the README's Eval Harness
section for the full writeup). Its prompt calls `sneaker_agent` "the
default for anything sneaker-related," which biased it away from
`inventory_agent` whenever shopping language was present at all.

`_mentions_existing_collection` closes this deterministically — matching
text routes straight to `inventory_agent` without an LLM call, and
`inventory_agent`'s own downstream check hands off to `sneaker_agent` if it
detects shopping intent too.

Pure function — no LLM calls, so this covers the routing decision without
depending on live model output.

| # | Case | Expected | Edge case covered |
|---|------|----------|--------------------|
| 12.1 | The exact TC-003 input (collection + shopping in one message) | routes to inventory_agent | the original bug report |
| 12.2 | "what is in my collection" / "see my collection" / "check my current collection" | routes to inventory_agent | viewing-verb phrasings |
| 12.3 | "add to my collection" / "new heat for my collection" | does NOT route to inventory_agent | "collection" as a shopping target, not a check, must not false-positive |
| 12.4 | Style/stock/minimal queries with no collection language | does NOT route to inventory_agent | no false positives on unrelated requests |

## Maintenance

Update this file and `cli_test.py` together whenever a feature is added or a
route changes, so the documented coverage stays in sync with the harness.
