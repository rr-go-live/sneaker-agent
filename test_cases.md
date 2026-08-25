# Test Cases — Sneaker Agent

This project has two complementary test layers:

1. **CLI test harness** ([`cli_test.py`](cli_test.py)) — fast structural and
   integration checks (parser, API routes, database, and one full pipeline
   run). Run it with `python cli_test.py`. See
   [CLI Test Harness](#cli-test-harness-cli_testpy) below.
2. **Eval harness** — quality scoring of the multi-agent routing and picks
   across realistic prompts. Run the full suite with `python eval_runner.py`
   or a single case with `python eval_runner.py --id TC-001`.

---

## Scoring Dimensions

There is no budget concept in this app — sneaker_agent has no price ceiling,
so there's no "budget accuracy" or "budget compliance" dimension.

| Dimension | What it checks | Agents involved |
|---|---|---|
| Routing Accuracy | Did the orchestrator pick the correct first agent? | orchestrator |
| Sneaker Validity | Are all proposed sneakers real catalog items (no hallucination)? | sneaker_agent |
| Failure Handling | Does the system return a graceful error message instead of crashing? | (none currently exercise this — see TC list below) |
| Latency | Did the full run finish within the acceptable time window (< 15s)? | all |

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

**What it validates:** The most complex routing path. The request contains both "see collection" and "buy new" intent. The orchestrator must detect the inventory-check intent first.

**Known failure mode:** When both intents are present, the orchestrator sometimes routes to sneaker_agent first (skipping inventory_agent). This is a genuine routing ambiguity — the eval harness surfaces it consistently. **Fix**: strengthen the orchestrator routing prompt to prioritize inventory_agent when "already own" language appears.

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

## Running Results Interpretation

- **All dimensions 100%** — pipeline is healthy
- **Routing Accuracy drops** — orchestrator prompt needs tuning; check which query types misroute
- **Sneaker Validity drops** — LLM is hallucinating catalog names; the catalog-validation logic in sneaker_agent may need strengthening
- **Failure Handling shows n/a** — expected; no current test case sets `is_failure_case: True` since there's no unresolvable-budget error path anymore. Add one back if a real failure path is introduced.
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

## Maintenance

Update this file and `cli_test.py` together whenever a feature is added or a
route changes, so the documented coverage stays in sync with the harness.
