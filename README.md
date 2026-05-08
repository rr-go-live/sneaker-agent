# Sneaker Agent — Multi-Agent System with Eval Harness

A multi-agent AI system built with **LangGraph** and **Gemini Flash**. Four specialized agents collaborate through shared state to handle the full sneaker shopping experience. A built-in **eval harness** scores the pipeline across six dimensions: routing accuracy, budget accuracy, sneaker validity, budget compliance, failure handling, and latency.

> The eval layer is the differentiated part — most multi-agent demos stop at the agents. This one measures them.

---

## How it works

Every request enters the **orchestrator**, which uses the LLM to route it to the right starting agent. Agents hand off to each other by writing to a shared `AgentState` TypedDict that travels through the graph.

```
User request
     │
     ▼
orchestrator  (LLM picks which agent handles this)
     │
     ├─→ financial_agent  →  sneaker_agent  →  logistics_agent  →  END
     │
     ├─→ inventory_agent  →  (if shopping intent) financial_agent  →  ...
     │
     └─→ logistics_agent  →  END
```

| Agent | Responsibility |
|---|---|
| `orchestrator` | Routes the user's request to the right first agent using the LLM |
| `financial_agent` | Looks up the user's budget from the data catalog |
| `sneaker_agent` | Asks the LLM to pick 2-3 catalog sneakers within budget |
| `inventory_agent` | Summarizes owned collection; uses LLM to decide whether to continue shopping |
| `logistics_agent` | Checks stock, shows retail vs market value, outputs StockX links |

Sneaker data is sourced from the [purplebugs/sneakers-game](https://github.com/purplebugs/sneakers-game/blob/main/data/sneakersFromDatabase.json) dataset (15 curated entries).

---

## Eval Harness

The eval harness runs the agent graph against 8 test cases and scores each run on 6 dimensions.

```
python eval_runner.py                # run all 8 test cases
python eval_runner.py --id TC-001   # run one specific test case
python eval_runner.py --verbose     # show agent logs during runs
```

### Scoring Dimensions

| Dimension | What it checks |
|---|---|
| **Routing Accuracy** | Did the orchestrator's LLM decision pick the right first agent? |
| **Budget Accuracy** | Did financial_agent retrieve the correct dollar amount? |
| **Sneaker Validity** | Are all proposed sneakers real catalog items? (catches LLM hallucination) |
| **Budget Compliance** | Does the total retail price stay within the user's budget? |
| **Failure Handling** | Does the system return a readable error instead of crashing on bad input? |
| **Latency** | Did the full run finish under the 15-second threshold? |

### Example Report

```
==============================================================================
  SNEAKER AGENT — EVAL REPORT
==============================================================================
  8 test cases  |  7/8 passed  |  total time: 54.2s  |  overall score: 98%

------------------------------------------------------------------------------
  ID        Test Case                               Score    Time  Status
------------------------------------------------------------------------------
  TC-001    Direct shopping request                 100%   13.3s  PASS
  TC-002    Collection check only — no shopping     100%    5.2s  PASS
  TC-003    Full 4-agent upgrade chain               80%   11.1s  FAIL
  TC-004    Style advice — no buying intent         100%    2.4s  PASS
  TC-005    Stock availability check                100%    0.8s  PASS
  TC-006    Unknown user — graceful failure         100%    1.4s  PASS
  TC-007    Alice shopping — $500 budget            100%    9.7s  PASS
  TC-008    Minimal query — no crash                100%   10.1s  PASS

------------------------------------------------------------------------------
  SCORES BY DIMENSION
------------------------------------------------------------------------------
  Routing Accuracy      █████████████████░░░  6/7 cases  86%
  Budget Accuracy       ████████████████████  3/3 cases  100%
  Sneaker Validity      ████████████████████  3/3 cases  100%
  Budget Compliance     ████████████████████  3/3 cases  100%
  Failure Handling      ████████████████████  1/1 cases  100%
  Latency               ████████████████████  8/8 cases  100%
```

**TC-003 failure is a real finding:** when both "see my collection" and "buy new" intent appear in one message, the orchestrator routes to `financial_agent` first and skips `inventory_agent`. The eval surfaces this consistently — the fix is to strengthen the orchestrator prompt to detect collection-check language before shopping language.

See [test_cases.md](test_cases.md) for full test case documentation and edge case notes.

---

## Prerequisites

- Python 3.10+
- A Google Gemini API key ([get one free here](https://aistudio.google.com/app/apikey))

---

## Setup

```bash
# 1. Clone the repo
git clone <repo-url>
cd sneaker-agent

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install langchain-google-genai langgraph

# 4. Add your API key
echo 'export GOOGLE_API_KEY="your-key-here"' > .env
source .env
```

---

## Running

**Demo — three hardcoded scenarios:**
```bash
python main.py
```

**Eval — scored report across 8 test cases:**
```bash
python eval_runner.py
```

---

## Project Structure

```
sneaker-agent/
├── main.py                  Entry point — runs 3 demo scenarios
├── eval_runner.py           CLI entry point for the eval harness
├── graph.py                 build_graph() — wires all agents into LangGraph
├── orchestrator.py          orchestrator() + router() — LLM routing logic
├── state.py                 AgentState TypedDict shared across all agents
├── llm.py                   Shared Gemini Flash LLM instance
│
├── agents/
│   ├── financial_agent.py   Looks up user budget
│   ├── sneaker_agent.py     LLM picks 2-3 sneakers within budget
│   ├── inventory_agent.py   Reviews collection; decides whether to shop
│   └── logistics_agent.py   Checks stock, retail vs market price, StockX links
│
├── data/
│   └── catalog.py           USER_BUDGETS, USER_SNEAKER_COLLECTION, SNEAKER_CATALOG
│
├── evals/
│   ├── cases.py             8 test case definitions with expected outcomes
│   ├── scorers.py           6 scoring functions (one per eval dimension)
│   ├── runner.py            Streams cases through graph, captures per-node results
│   └── report.py            Formats and prints the scored eval report
│
├── architecture/
│   └── diagram.md           Full system architecture diagram
└── test_cases.md            Test case documentation with edge cases
```

---

## Architecture

See [architecture/diagram.md](architecture/diagram.md) for the full system diagram including agent routing paths, data flow, and technology choices.

---

## Modifying Test Data

All static data lives in [data/catalog.py](data/catalog.py):

- **Add a user**: add an entry to `USER_BUDGETS` and `USER_SNEAKER_COLLECTION`
- **Change a budget**: update the dollar value in `USER_BUDGETS`
- **Edit the catalog**: add or modify entries in `SNEAKER_CATALOG`

To add a new eval test case, append a dict to `TEST_CASES` in [evals/cases.py](evals/cases.py) following the existing schema.
