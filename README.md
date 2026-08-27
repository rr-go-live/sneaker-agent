# Sneaker Agent — Multi-Agent System with React UI

A multi-agent AI system built with **LangGraph**, **Gemini Flash**, **FastAPI**, and **React**. Specialized agents collaborate through shared state to handle the full sneaker shopping experience — routing, inventory review, recommendation, critique, bidding, and logistics. There is no *account budget* — no balance is tracked and nothing is unaffordable, so any sneaker can be searched for and added to a wardrobe. Retail and market price are shown throughout as reference data, and a price ceiling the shopper states themselves ("under $150") is honored as a filter like any other constraint. Adding a sneaker to a wardrobe decrements it from the shared inventory. A built-in **eval harness** scores the pipeline across seven dimensions.

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
| `sneaker_agent`   | Resolves the shopper's constraints — brand, colorway, silhouette, price ceiling, release year, ordering — from the UI's filter chips *or* from free text, hard-filters the catalog to match, then asks the LLM to pick from that pool for style; accepts critique feedback on retry |
| `inventory_agent` | Reviews owned collection; uses LLM to decide whether to continue shopping                                                                                |
| `critique_agent`  | Deterministically checks pick count and brand compliance, then asks the LLM to judge value and (when no brand was requested) brand diversity — approves or rejects with a reason, up to 2 retries before force-approving |
| `logistics_agent` | Checks live DB inventory and reports retail vs market value. Emits structured rows the web UI renders as a table, plus an aligned plain-text version for the CLI |
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

The eval harness scores 15 test cases across 7 dimensions. Most run the full
agent graph; three run `bid_agent` directly, since bidding targets one
already-known sneaker rather than a routing decision (see `kind` in
[evals/cases.py](evals/cases.py)).

```bash
python eval_runner.py                # run all 15 test cases
python eval_runner.py --id TC-001   # run one specific test case
python eval_runner.py --verbose     # show agent logs during runs
```

### Scoring Dimensions

| Dimension                  | What it checks                                                              | Applies to           |
| --------------------------- | ---------------------------------------------------------------------------- | --------------------- |
| **Routing Accuracy**  | Did the orchestrator pick the right first agent?                            | graph cases           |
| **Sneaker Validity**  | Are all proposed sneakers real catalog items? (catches hallucination)       | graph cases           |
| **Expected Pick**     | Does one specific correct catalog item actually appear in the picks?        | graph cases           |
| **Constraint Fidelity** | Does every pick honor the brand, silhouette, price ceiling and release year the user asked for? | graph cases |
| **Bid Fairness**      | Does `bid_agent` accept/reject in line with real market data?             | bid cases             |
| **Failure Handling**  | Does the system return a readable error instead of crashing on bad input?   | any                    |
| **Latency**           | Did the full run finish under the 15-second threshold?                      | all                    |

There is no account-budget concept, so nothing scores "can the user afford this". A stated ceiling is scored under Constraint Fidelity, alongside brand and silhouette.

### Example Report

```
==============================================================================
  SNEAKER AGENT — EVAL REPORT
==============================================================================
  15 test cases  |  15/15 passed  |  total time: 161.8s  |  overall score: 93%

------------------------------------------------------------------------------
  ID        Test Case                               Score    Time  Status
------------------------------------------------------------------------------
  TC-001    Direct shopping request                 100%   12.4s  PASS
  TC-002    Collection check only — no shopping     100%    3.5s  PASS
  TC-003    Inventory review then shopping           83%   20.4s  PASS
  TC-004    Style advice request                    100%   11.1s  PASS
  TC-005    Stock availability check                100%    1.0s  PASS
  TC-006    Alice shopping request                   83%   15.2s  PASS
  TC-007    Minimal query — no crash                 50%   19.9s  PASS
  TC-008    Lowball bid rejected                    100%    2.5s  PASS
  TC-009    Fair bid accepted                       100%    3.0s  PASS
  TC-010    Bid on unknown sneaker rejected         100%    0.0s  PASS
  TC-011    Highest retail Jordans post-2022        100%   10.9s  PASS
  TC-012    Free-text brand + silhouette + budget    88%   27.9s  PASS
  TC-013    Cheapest New Balance                    100%    8.0s  PASS
  TC-014    Colorway + brand + budget stack          88%   25.0s  PASS
  TC-015    Impossible budget fails honestly        100%    1.3s  PASS

------------------------------------------------------------------------------
  SCORES BY DIMENSION
------------------------------------------------------------------------------
  Routing Accuracy      ████████████████████  11/11 cases  100%
  Sneaker Validity      ████████████████████  8/8 cases  100%
  Expected Pick         ████████████████████  1/1 cases  100%
  Constraint Fidelity   ████████████████████  4/4 cases  100%
  Bid Fairness          ████████████████████  3/3 cases  100%
  Failure Handling      ████████████████████  2/2 cases  100%
  Latency               █████████████████░░░  10/15 cases  83%
```

**TC-003 was a real, non-flaky bug, now fixed:** a compound request — one that both references the existing collection AND asks for new picks — was routed to `sneaker_agent` by the LLM orchestrator 5/5 times, skipping `inventory_agent` entirely. Its prompt calls `sneaker_agent` "the default for anything sneaker-related," which biased it away from `inventory_agent` whenever shopping language was present at all, with no rule for handling both intents in one message. Fixed with a deterministic pre-check (`orchestrator._mentions_existing_collection`) that routes collection-referencing language straight to `inventory_agent` without an LLM call — `inventory_agent`'s own downstream check still hands off to `sneaker_agent` if it detects shopping intent, so the compound request still reaches both agents, just in the right order.

**Latency is the weakest dimension, and it is genuine.** `sneaker_agent` sends up to `MAX_CATALOG_SIZE` (80) catalog rows to Gemini and regularly takes 15–30s, which is what drags the score to 77%. The threshold is deliberately left at 15s rather than raised to make the number look better — the slow calls are real, and hiding them would defeat the point of measuring.

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

A diagrammed version of the end-to-end data flow — including the routing/retry loop and both side paths — is here: [Sneaker Agent Architecture](https://claude.ai/code/artifact/070023f9-56d4-4258-a81c-fee60be23445).

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
