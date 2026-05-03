# Agentic AI Sneaker Shopping System

A multi-agent AI system built with **LangGraph** and **Gemini Flash**. Five specialized agents collaborate through shared state to handle every step of the sneaker shopping experience — from reviewing your collection to checking availability and pricing.

---

## How it works

Every request enters the **orchestrator**, which uses the LLM to route it to the right starting agent. Agents hand off to each other by writing to a shared `AgentState` object that travels through the graph.

```
User request
     │
     ▼
orchestrator
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
| `financial_agent` | Looks up the user's budget |
| `sneaker_agent` | Asks the LLM to pick 2-3 sneakers from the catalog within budget |
| `inventory_agent` | Reviews what the user already owns; decides via LLM whether to continue shopping |
| `logistics_agent` | Checks stock, shows retail price vs market value, and provides a StockX link |

Sneaker data is sourced from the [purplebugs/sneakers-game](https://github.com/purplebugs/sneakers-game/blob/main/data/sneakersFromDatabase.json) dataset (15 curated entries).

---

## Prerequisites

- Python 3.10+
- A Google Gemini API key ([get one free here](https://aistudio.google.com/app/apikey))

---

## Setup

```bash
# 1. Clone the repo
git clone <repo-url>
cd multi-agent

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install langchain-google-genai langgraph

# 4. Add your API key
echo 'export GOOGLE_API_KEY="your-key-here"' > .env
```

---

## Running the demo

```bash
source .venv/bin/activate
source .env
python main.py
```

The script runs three scenarios back to back:

| Scenario | User | Query | Agent chain |
|---|---|---|---|
| 1 | John ($300) | "Help me find some fresh kicks" | orchestrator → financial_agent → sneaker_agent → logistics_agent |
| 2 | Alice ($500) | "What sneakers do I already own?" | orchestrator → inventory_agent → END |
| 3 | John ($300) | "Upgrade my collection within budget" | orchestrator → inventory_agent → financial_agent → sneaker_agent → logistics_agent |

---

## Example output

```
Sneaker Availability Report:

  - New Balance 550 Triple Black (New Balance)  |  Black/Black/Black  |  IN STOCK  |  Retail: $110.0  |  Market: $146.0  |  https://stockx.com/new-balance-550-triple-black
  - Adidas Busenitz Vintage Focus Orange (Adidas)  |  Focus Orange/Cloud White/Gum  |  IN STOCK  |  Retail: $85.0  |  Market: $100.0  |  https://stockx.com/adidas-busenitz-vintage-focus-orange
  - Nike SB Dunk High Oski Great White (Nike)  |  White/Cool Grey-White-White  |  IN STOCK  |  Retail: $100.0  |  Market: $364.0  |  https://stockx.com/nike-sb-dunk-high-oski-great-white

  Estimated retail total: $295.0
```

---

## Project structure

```
multi-agent/
├── main.py               # Entry point — builds the graph and runs demo scenarios
├── graph.py              # build_graph() — wires all agents into the LangGraph
├── orchestrator.py       # orchestrator() + router() — LLM-based routing logic
├── state.py              # AgentState TypedDict shared across all agents
├── llm.py                # Shared Gemini Flash LLM instance
├── data/
│   └── catalog.py        # USER_BUDGETS, USER_SNEAKER_COLLECTION, SNEAKER_CATALOG
└── agents/
    ├── financial_agent.py   # Looks up the user's budget
    ├── sneaker_agent.py     # Asks LLM to pick sneakers within budget
    ├── inventory_agent.py   # Reviews owned sneakers; decides whether to shop
    └── logistics_agent.py   # Checks stock, shows pricing, outputs StockX links
```

---

## Modifying test data

All static data lives in [data/catalog.py](data/catalog.py):

- **Add a user**: add an entry to `USER_BUDGETS` and `USER_SNEAKER_COLLECTION`
- **Change a budget**: update the dollar value in `USER_BUDGETS`
- **Edit the catalog**: add or modify entries in `SNEAKER_CATALOG`
# sneaker-agent
