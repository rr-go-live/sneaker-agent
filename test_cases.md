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

| Dimension | What it checks | Agents involved |
|---|---|---|
| Routing Accuracy | Did the orchestrator pick the correct first agent? | orchestrator |
| Budget Accuracy | Did financial_agent find the right dollar amount? | financial_agent |
| Sneaker Validity | Are all proposed sneakers real catalog items (no hallucination)? | sneaker_agent |
| Budget Compliance | Does the total retail price stay within the user's budget? | sneaker_agent |
| Failure Handling | Does the system return a graceful error message instead of crashing? | financial_agent |
| Latency | Did the full run finish within the acceptable time window (< 15s)? | all |

---

## Test Cases

### TC-001 — Direct Shopping Request
| Field | Value |
|---|---|
| Input | "Help me find some fresh kicks to add to my collection" |
| User | John ($300) |
| Expected chain | orchestrator → financial_agent → sneaker_agent → logistics_agent |
| Expected first agent | financial_agent |
| Expected budget | $300.00 |
| Check budget compliance | Yes |

**What it validates:** The most common happy path. Shopping intent must route directly to financial_agent, the LLM must pick sneakers that fit within $300, and all names must be real catalog entries.

**Edge cases:** Sneaker prices must sum to ≤ $300. Partial results (2 sneakers instead of 3) are allowed.

---

### TC-002 — Collection Check Only (No Shopping)
| Field | Value |
|---|---|
| Input | "What sneakers do I already have in my collection?" |
| User | Alice ($500) |
| Expected chain | orchestrator → inventory_agent → END |
| Expected first agent | inventory_agent |
| Expected budget | None |
| Check budget compliance | No |

**What it validates:** Pure collection-review intent should stop at inventory_agent. No financial_agent or sneaker_agent should run. Tests the LLM-based routing decision inside inventory_agent.

**Edge cases:** If inventory_agent's internal LLM misreads the intent as "shop", financial_agent will run unexpectedly. This is a known flakiness risk.

---

### TC-003 — Full 4-Agent Upgrade Chain
| Field | Value |
|---|---|
| Input | "I want to upgrade my sneaker collection. What do I already own, and what new heat can I cop to complete the rotation within budget?" |
| User | John ($300) |
| Expected chain | orchestrator → inventory_agent → financial_agent → sneaker_agent → logistics_agent |
| Expected first agent | inventory_agent |
| Expected budget | $300.00 |
| Check budget compliance | Yes |

**What it validates:** The most complex routing path. The request contains both "see collection" and "buy new" intent. The orchestrator must detect the inventory-check intent first.

**Known failure mode:** When both intents are present, the orchestrator sometimes routes to financial_agent first (skipping inventory_agent). This is a genuine routing ambiguity — the eval harness surfaces it consistently. **Fix**: strengthen the orchestrator routing prompt to prioritize inventory_agent when "already own" language appears.

---

### TC-004 — Style Advice Only (No Buying)
| Field | Value |
|---|---|
| Input | "What are the hottest sneaker styles and trends right now?" |
| User | John |
| Expected chain | orchestrator → sneaker_agent |
| Expected first agent | sneaker_agent |
| Expected budget | None |
| Check budget compliance | No |

**What it validates:** Pure style queries with no buying intent should bypass financial_agent entirely and route directly to sneaker_agent. Tests the orchestrator's ability to distinguish "I want to buy" from "I want advice."

---

### TC-005 — Stock Availability Check
| Field | Value |
|---|---|
| Input | "Is the Jordan 4 Retro Infrared available in the store right now?" |
| User | John |
| Expected chain | orchestrator → logistics_agent |
| Expected first agent | logistics_agent |
| Expected budget | None |
| Check budget compliance | No |

**What it validates:** Asking about a specific named sneaker's stock status should go straight to logistics_agent without running any other agent. Note: logistics_agent reports "No sneakers to check" because it reads from `proposed_sneakers` (set by sneaker_agent), which is empty on a direct route. This is a known gap in the current implementation.

---

### TC-006 — Unknown User (Graceful Failure)
| Field | Value |
|---|---|
| Input | "Help me find some cool sneakers" |
| User | Bob (not in USER_BUDGETS) |
| Expected chain | orchestrator → financial_agent → END |
| Expected first agent | financial_agent |
| Is failure case | Yes |
| Expected output contains | "could not find a budget" |

**What it validates:** When a user has no budget on record, financial_agent must return a readable error message and stop the chain cleanly. The system must not crash, and the output must contain a user-friendly error string.

**Edge cases:** Any exception raised by the agent chain counts as a failure, even if the error message would have been correct.

---

### TC-007 — Alice Shopping ($500 Budget)
| Field | Value |
|---|---|
| Input | "I want to buy some new heat for my collection" |
| User | Alice ($500) |
| Expected chain | orchestrator → financial_agent → sneaker_agent → logistics_agent |
| Expected first agent | financial_agent |
| Expected budget | $500.00 |
| Check budget compliance | Yes |

**What it validates:** Verifies the system works correctly for a second user with a different budget. Alice's $500 gives sneaker_agent more catalog options — compliance check confirms the LLM still stays within bounds.

---

### TC-008 — Minimal One-Word Query (No Crash)
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
- **Budget Compliance drops** — sneaker_agent is selecting picks that exceed the user's budget; prompt refinement needed
- **Failure Handling drops** — an error path is crashing instead of returning a message; check agent error handling
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

## 5. Full multi-agent pipeline (`graph.build_graph`)

Runs a complete buying request through the graph
(orchestrator → financial → sneaker → critique → logistics).

**Input:**
```python
{
  "input": "I want a clean white low-top for everyday wear that holds resale value",
  "user_name": "cli_test_user",
  "budget": 300.0,
}
```

| # | Expected output | Edge case covered |
|---|-----------------|-------------------|
| 5.1 | Visits `orchestrator` and `sneaker_agent` | Routing works for shopping intent |
| 5.2 | **Every** node emits non-empty `reasoning` | Powers the Logging tab's step-by-step LLM reasoning |
| 5.3 | `proposed_sneakers` has ≥ 1 pick | Sneaker agent produces output |
| 5.4 | Total retail of picks ≤ `budget` | Budget compliance enforced end to end |

**Skip condition:** reported `SKIP` when no real `GOOGLE_API_KEY` is set,
since it makes live Gemini calls. The harness still exits successfully.

## Maintenance

Update this file and `cli_test.py` together whenever a feature is added or a
route changes, so the documented coverage stays in sync with the harness.
