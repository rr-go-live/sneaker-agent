# Sneaker Agent — Multi-Agent System with React UI

A multi-agent AI system built with **LangGraph**, **Gemini Flash**, **FastAPI**, and **React**. Five specialized agents collaborate through shared state to handle the full sneaker shopping experience — routing, budgeting, inventory review, recommendation, critique, and logistics. A built-in **eval harness** scores the pipeline across six dimensions.

> The eval layer is the differentiated part — most multi-agent demos stop at the agents. This one measures them.

---

## How it works

Every request enters the **orchestrator**, which uses the LLM to route it to the right starting agent. Agents hand off by writing to a shared `AgentState` TypedDict that travels through the graph.

```
User request (web UI or CLI eval)
         │
         ▼
   orchestrator  (LLM picks which agent handles this)
         │
         ├─→ financial_agent → sneaker_agent → critique_agent → logistics_agent → END
         │
         ├─→ inventory_agent → (if shopping intent) financial_agent → ...
         │
         └─→ logistics_agent → END
```

| Agent               | Responsibility                                                                                                                                           |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `orchestrator`    | Routes the user's request to the right first agent using the LLM                                                                                         |
| `financial_agent` | Looks up the user's budget from the database (falls back to catalog.py)                                                                                  |
| `sneaker_agent`   | Asks the LLM to pick 2–3 catalog sneakers within budget; accepts critique feedback on retry                                                             |
| `inventory_agent` | Reviews owned collection; uses LLM to decide whether to continue shopping                                                                                |
| `critique_agent`  | Reviews picks against three rubrics (budget, market value, brand diversity); approves or rejects with a reason — up to 2 retries before force-approving |
| `logistics_agent` | Checks live DB inventory, shows retail vs market value, outputs StockX links                                                                             |

Sneaker data comes from `data/sneakerdata.json` — **1,668 real sneakers** with full StockX market data (retail price, market value, last sale, lowest ask, deadstock sold).

---

## Web UI

A React + Vite SPA (port `5173`) with three pages:

| Page              | What it does                                                                                                |
| ----------------- | ----------------------------------------------------------------------------------------------------------- |
| **Advisor** | Natural language input form — streams each agent step in real time and renders the final sneaker picks     |
| **Catalog** | Browsable catalog of all 1,668 sneakers with search, brand, profile, price, and in-stock filters            |
| **Evals**   | Runs the eval harness from the browser — streams each test case as it finishes and shows the scored report |

---

## API

The FastAPI backend (port `8000`) exposes the following endpoints:

| Method     | Path                                      | Description                                                                                     |
| ---------- | ----------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `GET`    | `/api/sneakers`                         | Full catalog with optional filters (`q`, `brand`, `profile`, `max_price`, `in_stock`) |
| `POST`   | `/api/agent`                            | Runs the agent graph — SSE stream of agent steps + final result                                |
| `POST`   | `/api/evals/run`                        | Runs the eval harness — SSE stream of test case results + summary                              |
| `GET`    | `/api/users`                            | List all user profiles                                                                          |
| `GET`    | `/api/users/{username}`                 | Single user profile with full wardrobe                                                          |
| `PUT`    | `/api/users/{username}`                 | Create or update a user's budget                                                                |
| `POST`   | `/api/users/{username}/wardrobe`        | Add a sneaker to a user's wardrobe                                                              |
| `DELETE` | `/api/users/{username}/wardrobe/{name}` | Remove a sneaker from a user's wardrobe                                                         |
| `GET`    | `/api/inventory/{sneaker_name}`         | Live stock quantity for one sneaker                                                             |
| `POST`   | `/api/inventory/purchase`               | Decrement inventory; optionally add to user's wardrobe                                          |

---

## Eval Harness

The eval harness runs the agent graph against 8 test cases and scores each run on 6 dimensions.

```bash
python eval_runner.py                # run all 8 test cases
python eval_runner.py --id TC-001   # run one specific test case
python eval_runner.py --verbose     # show agent logs during runs
```

### Scoring Dimensions

| Dimension                   | What it checks                                                            |
| --------------------------- | ------------------------------------------------------------------------- |
| **Routing Accuracy**  | Did the orchestrator pick the right first agent?                          |
| **Budget Accuracy**   | Did`financial_agent` retrieve the correct dollar amount?                |
| **Sneaker Validity**  | Are all proposed sneakers real catalog items? (catches hallucination)     |
| **Budget Compliance** | Does the total retail price stay within the user's budget?                |
| **Failure Handling**  | Does the system return a readable error instead of crashing on bad input? |
| **Latency**           | Did the full run finish under the 15-second threshold?                    |

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
- Node.js 18+ and npm
- A Google Gemini API key ([get one free](https://aistudio.google.com/app/apikey))

---

## Setup

```bash
# 1. Clone the repo
git clone <repo-url>
cd sneaker-agent

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install Python dependencies
pip install langchain-google-genai langgraph fastapi uvicorn sqlalchemy pydantic

# 4. Set your API key
export GOOGLE_API_KEY="your-key-here"

# 5. Seed the database (creates sneaker_agent.db with demo users and inventory)
python db_init.py

# 6. Install frontend dependencies
cd frontend && npm install && cd ..
```

---

## Running

**API backend** (terminal 1):

```bash
uvicorn api:app --reload
```

**React frontend** (terminal 2):

```bash
cd frontend && npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

**CLI eval harness** (no server required):

```bash
python eval_runner.py
```

---

## Project Structure

```
sneaker-agent/
├── api.py                   FastAPI app — REST + SSE endpoints
├── graph.py                 build_graph() — wires all agents into LangGraph
├── orchestrator.py          orchestrator() + router() — LLM routing logic
├── state.py                 AgentState TypedDict shared across all agents
├── llm.py                   Shared Gemini Flash LLM instance
├── database.py              SQLAlchemy models + helpers (SQLite)
├── db_init.py               Seeds demo users and store inventory on first run
├── eval_runner.py           CLI entry point for the eval harness
│
├── agents/
│   ├── financial_agent.py   Budget lookup (DB → catalog fallback)
│   ├── sneaker_agent.py     LLM picks 2–3 sneakers; handles critique retry feedback
│   ├── inventory_agent.py   Wardrobe lookup; decides whether to continue shopping
│   ├── critique_agent.py    Validates picks (budget, value, diversity); approve/reject loop
│   └── logistics_agent.py   Live DB inventory check; retail vs market; StockX links
│
├── data/
│   ├── catalog.py           Loads sneakerdata.json → SNEAKER_CATALOG dict
│   └── sneakerdata.json     1,668 sneakers with full StockX market data
│
├── evals/
│   ├── cases.py             8 test case definitions with expected outcomes
│   ├── scorers.py           6 scoring functions (one per eval dimension)
│   ├── runner.py            Streams cases through graph, captures per-node results
│   └── report.py            Formats and prints the scored eval report
│
├── frontend/                React + Vite SPA
│   └── src/
│       ├── pages/
│       │   ├── Advisor.jsx  AI recommendation form + live pipeline visualization
│       │   ├── Catalog.jsx  Filterable sneaker catalog with purchase flow
│       │   └── Evals.jsx    Browser-based eval runner with live scoring
│       ├── components/
│       │   ├── FilterBar.jsx     Search and filter controls
│       │   ├── LogPane.jsx       Agent step log with per-step LLM reasoning
│       │   ├── Nav.jsx           Top navigation bar
│       │   ├── SneakerCard.jsx   Flip card with purchase flow
│       │   └── SneakerPicker.jsx Wardrobe item selector
│       └── utils/
│           └── colors.js    Colorway → CSS color mapping
│
├── cli_test.py              CLI test harness (run: python cli_test.py)
└── test_cases.md            Test case documentation with edge cases
```

---

## Architecture

High-level end-to-end data flow:

```
Browser (React / Vite)
    │  HTTP / SSE
    ▼
FastAPI (api.py)
    │
    ▼
LangGraph Agent Graph
  orchestrator → financial_agent → sneaker_agent → critique_agent → logistics_agent
                 inventory_agent ↗                 ↺ retry (max 2)
    │
    ▼
SQLite Database (database.py)
  users · wardrobe_items · sneaker_inventory
    │
    ▼
data/sneakerdata.json  —  1,668 sneakers · StockX market data
```

---

## Modifying Test Data

**Catalog** — all sneaker data lives in [data/sneakerdata.json](data/sneakerdata.json). Add or edit entries directly; `catalog.py` loads it at import time.

**User profiles** — demo users (`john`, `alice`, `demo`) are seeded by `db_init.py` into `sneaker_agent.db`. To reset or change them, edit the `SEED_USERS` list in [db_init.py](db_init.py) and delete `sneaker_agent.db`, then re-run `python db_init.py`.

**Eval test cases** — append a dict to `TEST_CASES` in [evals/cases.py](evals/cases.py) following the existing schema.
