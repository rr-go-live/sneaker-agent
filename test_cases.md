# Test Cases — Sneaker Agent Eval Harness

Run the full suite: `python eval_runner.py`
Run a single case: `python eval_runner.py --id TC-001`

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
