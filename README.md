# Sneaker Agent — Multi-Agent System with React UI

A multi-agent AI system built with **LangGraph**, **Gemini Flash**, **FastAPI**, and **React**. Specialized agents collaborate through shared state to handle the full sneaker shopping experience — routing, inventory review, recommendation, critique, bidding, and logistics. There is no budget/price ceiling anywhere in the app — any sneaker can be searched for and added to a wardrobe regardless of cost; retail/market price is still shown throughout as reference data. Adding a sneaker to a wardrobe decrements it from the shared inventory. A built-in **eval harness** scores the pipeline across four dimensions.

---

## Key concepts

A few ideas come up throughout this codebase. Understanding them makes everything else easier to follow:

- **Agent** — a Python function that takes the current state, does one focused job (often by calling an LLM), and returns the fields it changed. Think of it as one step in an assembly line, not a whole program.
- **LangGraph** — the library that wires agents together into a graph and runs them in order, passing state from one to the next. It decides "who runs next" using the routing rules we define, so we don't have to hand-write a chain of if/else calls.
- **Shared state (`AgentState`)** — a single dictionary-like object ([state.py](state.py)) that every agent reads from and writes back to. Instead of agents calling each other directly, they all talk through this one shared object, which is what makes the pipeline easy to reorder or extend.
- **Orchestrator / router** — the traffic controller. The orchestrator asks the LLM "which agent should handle this request?" and the router uses that decision (plus the current state) to pick the next node in the graph.
- **Deterministic vs. LLM-judged checks** — some things (does this sneaker exist? is the count within range?) are checked with plain Python code because they have one correct answer. Other things (is this a fair bid? does this pick match the user's style?) are judgment calls, so those are handed to the LLM. Keeping the two separate makes the system more reliable — the LLM is only asked to decide things that actually require judgment.
- **Retry loop** — `sneaker_agent` and `critique_agent` can loop up to twice: critique rejects a set of picks with a reason, sneaker_agent tries again using that feedback, and after the retry limit the picks are force-approved so the app never gets stuck.

---

## How it works

Every request enters the **orchestrator**, which uses the LLM to route it to the right starting agent. Agents hand off by writing to a shared `AgentState` TypedDict that travels through the graph.

```
User request (web UI or CLI eval)
         │
         ▼
   orchestrator  (LLM picks which agent handles this)
         │
         ├─→ sneaker_agent → critique_agent → logistics_agent → END
         │
         ├─→ inventory_agent → (if shopping intent) sneaker_agent → ...
         │
         └─→ logistics_agent → END

Bidding runs outside the graph:
   user picks a known sneaker + bid amount → bid_agent → accept/reject
```

| Agent               | Responsibility                                                                                                                                           |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `orchestrator`    | Routes the user's request to the right first agent using the LLM                                                                                         |
| `sneaker_agent`   | Hard-filters the catalog by requested brand/color, then asks the LLM to pick from that pool to match style; accepts critique feedback on retry            |
| `inventory_agent` | Reviews owned collection; uses LLM to decide whether to continue shopping                                                                                |
| `critique_agent`  | Deterministically checks pick count and brand compliance, then asks the LLM to judge value and (when no brand was requested) brand diversity — approves or rejects with a reason, up to 2 retries before force-approving |
| `logistics_agent` | Checks live DB inventory, shows retail vs market value, outputs StockX links                                                                             |
| `bid_agent`       | Standalone (not part of the graph) — deterministically rejects invalid bids, then asks the LLM to judge fairness against real market data for one sneaker the user already picked |

Sneaker data comes from `data/sneakerdata.json` — **1,668 real sneakers** with full StockX market data (retail price, market value, last sale, lowest ask, deadstock sold).

---

## Web UI

A React + Vite SPA (port `5173`) with a login gate and four pages:

| Page              | What it does                                                                                                |
| ----------------- | ----------------------------------------------------------------------------------------------------------- |
| **Login**   | Username/password form; on success the session cookie gates access to the rest of the app                  |
| **Advisor** | Natural language input form — streams each agent step in real time and renders the final sneaker picks     |
| **Catalog** | Browsable catalog of all 1,668 sneakers with search, brand, profile, price, and in-stock filters; supports bidding on a specific pair |
| **Evals**   | Runs the eval harness from the browser — streams each test case as it finishes and shows the scored report |

Login state is held in `AuthContext` ([frontend/src/auth/AuthContext.jsx](frontend/src/auth/AuthContext.jsx)), which calls `/api/auth/me` on load to restore the session after a refresh.

---

## API

The FastAPI backend (port `8000`) exposes the following endpoints:

| Method     | Path                                      | Description                                                                                     |
| ---------- | ----------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `POST`   | `/api/auth/login`                       | Verifies username/password, starts a signed session cookie                                      |
| `POST`   | `/api/auth/logout`                      | Clears the session cookie                                                                       |
| `GET`    | `/api/auth/me`                          | Returns the logged-in user from the session, or 401                                             |
| `GET`    | `/api/sneakers`                         | Full catalog with optional filters (`q`, `brand`, `profile`, `max_price`, `in_stock`) |
| `POST`   | `/api/agent`                            | Runs the agent graph — SSE stream of agent steps + final result                                |
| `POST`   | `/api/bid`                              | Evaluates a bid on one sneaker against real market data — accept/reject with reasoning          |
| `POST`   | `/api/evals/run`                        | Runs the eval harness — SSE stream of test case results + summary                              |
| `GET`    | `/api/users`                            | List all user profiles                                                                          |
| `GET`    | `/api/users/{username}`                 | Single user profile with full wardrobe                                                          |
| `POST`   | `/api/users/{username}/wardrobe`        | Add a sneaker to a user's wardrobe                                                              |
| `DELETE` | `/api/users/{username}/wardrobe/{name}` | Remove a sneaker from a user's wardrobe                                                         |
| `GET`    | `/api/inventory/{sneaker_name}`         | Live stock quantity for one sneaker                                                             |
| `POST`   | `/api/inventory/purchase`               | Decrement inventory; optionally add to user's wardrobe                                          |

Passwords are never stored in plaintext — [auth.py](auth.py) hashes them with PBKDF2-HMAC-SHA256 (260,000 iterations, per-user random salt), the current OWASP-recommended minimum for this algorithm.

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
| **Sneaker Validity**  | Are all proposed sneakers real catalog items? (catches hallucination)     |
| **Failure Handling**  | Does the system return a readable error instead of crashing on bad input? |
| **Latency**           | Did the full run finish under the 15-second threshold?                    |

There is no budget concept in this app, so there's no budget-related scoring dimension.

### Example Report

```
==============================================================================
  SNEAKER AGENT — EVAL REPORT
==============================================================================
  7 test cases  |  6/7 passed  |  total time: 48.6s  |  overall score: 97%

------------------------------------------------------------------------------
  ID        Test Case                               Score    Time  Status
------------------------------------------------------------------------------
  TC-001    Direct shopping request                 100%   12.8s  PASS
  TC-002    Collection check only — no shopping     100%    5.2s  PASS
  TC-003    Inventory review then shopping           80%   11.1s  FAIL
  TC-004    Style advice request                    100%    9.4s  PASS
  TC-005    Stock availability check                100%    0.8s  PASS
  TC-006    Alice shopping request                  100%    9.7s  PASS
  TC-007    Minimal query — no crash                100%    9.9s  PASS

------------------------------------------------------------------------------
  SCORES BY DIMENSION
------------------------------------------------------------------------------
  Routing Accuracy      █████████████████░░░  6/7 cases  86%
  Sneaker Validity      ████████████████████  5/5 cases  100%
  Failure Handling      ────────────────────  0/0 cases   n/a
  Latency               ████████████████████  7/7 cases  100%
```

**TC-003 failure is a real finding:** when both "see my collection" and "buy new" intent appear in one message, the orchestrator sometimes routes to `sneaker_agent` first and skips `inventory_agent`. The eval surfaces this consistently — the fix is to strengthen the orchestrator prompt to detect collection-check language before shopping language.

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
├── api.py                   FastAPI app — REST + SSE endpoints, session auth
├── auth.py                  Password hashing/verification (PBKDF2-HMAC-SHA256)
├── graph.py                 build_graph() — wires all agents into LangGraph
├── orchestrator.py          orchestrator() + router() — LLM routing logic
├── state.py                 AgentState TypedDict shared across all agents
├── llm.py                   Shared Gemini Flash LLM instance
├── database.py              SQLAlchemy models + helpers (SQLite)
├── db_init.py               Seeds demo users and store inventory on first run
├── eval_runner.py           CLI entry point for the eval harness
│
├── agents/
│   ├── selection.py         Deterministic brand/color filtering + count parsing/validation
│   ├── sneaker_agent.py     Hard-filters by brand/color, then LLM picks to match style; handles critique retry feedback
│   ├── inventory_agent.py   Wardrobe lookup; decides whether to continue shopping
│   ├── critique_agent.py    Validates picks (count, brand, value, diversity); approve/reject loop
│   ├── logistics_agent.py   Live DB inventory check; retail vs market; StockX links
│   └── bid_agent.py         Standalone — judges whether a bid on one sneaker is fair vs. market data
│
├── data/
│   ├── catalog.py           Loads sneakerdata.json → SNEAKER_CATALOG dict
│   └── sneakerdata.json     1,668 sneakers with full StockX market data
│
├── evals/
│   ├── cases.py             Test case definitions with expected outcomes
│   ├── scorers.py           Scoring functions (one per eval dimension)
│   ├── runner.py            Streams cases through graph, captures per-node results
│   └── report.py            Formats and prints the scored eval report
│
├── frontend/                React + Vite SPA
│   └── src/
│       ├── auth/
│       │   └── AuthContext.jsx  Session state; calls /api/auth/me on load
│       ├── pages/
│       │   ├── Login.jsx    Username/password form
│       │   ├── Advisor.jsx  AI recommendation form + live pipeline visualization
│       │   ├── Catalog.jsx  Filterable sneaker catalog with purchase + bid flow
│       │   └── Evals.jsx    Browser-based eval runner with live scoring
│       ├── components/
│       │   ├── LogPane.jsx       Agent step log with per-step LLM reasoning
│       │   ├── Nav.jsx           Top navigation bar
│       │   └── SneakerCard.jsx   Flip card with purchase + bid flow
│       └── utils/
│           └── reference.js Shared UI reference data/helpers
│
├── cli_test.py              CLI test harness (run: python cli_test.py)
└── test_cases.md            Test case documentation with edge cases
```

---

## Architecture

High-level end-to-end data flow:

```
Browser (React / Vite)
    │  HTTP / SSE, session cookie
    ▼
FastAPI (api.py)
  ├── /api/auth/*       → auth.py (password hashing) + database.py (session lookup)
  ├── /api/agent        → LangGraph Agent Graph (below)
  ├── /api/bid          → bid_agent.py (standalone, not part of the graph)
  └── /api/sneakers, /api/users, /api/inventory → database.py + data/catalog.py

LangGraph Agent Graph
  orchestrator → sneaker_agent → critique_agent → logistics_agent
                 inventory_agent ↗              ↺ retry (max 2)
    │
    ▼
SQLite Database (database.py)
  users · wardrobe_items · sneaker_inventory  (no budget/price ceiling anywhere)
    │
    ▼
data/sneakerdata.json  —  1,668 sneakers · StockX market data
```

A diagrammed version of this flow — including the routing/retry loop and both side paths — is here: [Sneaker Agent Architecture](https://claude.ai/code/artifact/070023f9-56d4-4258-a81c-fee60be23445).

---

## Modifying Test Data

**Catalog** — all sneaker data lives in [data/sneakerdata.json](data/sneakerdata.json). Add or edit entries directly; `catalog.py` loads it at import time.

**Catalog photos** — sneaker cards show a real product photo when a catalog entry has an `image` field, and fall back to the colorway-derived color swatch otherwise. Photos are backfilled offline (never fetched at request time) via [backfill_images.py](backfill_images.py), which calls the [KicksDB](https://kicks.dev) StockX API. Setup:
1. Create a free KicksDB account and generate an API key.
2. Add `KICKS_API_KEY=<your key>` to `.env`.
3. Run `python backfill_images.py`.

**Cost note:** the free tier caps requests at 1,000/month; the catalog has 1,668 entries. The script prioritizes the most-viewed sneakers (by `sales_this_period`) and is resumable — it skips anything already fetched and marks permanent no-matches so they're never re-queried, so re-running it next billing cycle picks up where it left off at no extra cost.

**User profiles** — demo users (`john`, `alice`, `demo`) are seeded by `db_init.py` into `sneaker_agent.db`. To reset or change them, edit the `SEED_USERS` list in [db_init.py](db_init.py) and delete `sneaker_agent.db`, then re-run `python db_init.py`.

**Eval test cases** — append a dict to `TEST_CASES` in [evals/cases.py](evals/cases.py) following the existing schema.
