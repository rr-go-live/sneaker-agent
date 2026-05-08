# Architecture — Sneaker Agent System

## System Overview

```
User Input (text query + user name)
        │
        ▼
┌───────────────────────────────────────────────────────────────────────┐
│                         LangGraph Agent Graph                         │
│                                                                       │
│   ┌─────────────┐                                                     │
│   │ orchestrator│  ← LLM routing decision (Gemini Flash)             │
│   └──────┬──────┘                                                     │
│          │                                                            │
│    ┌─────┴──────────────────────────┐                                │
│    │             route              │                                 │
│    ▼             ▼         ▼        ▼                                 │
│  financial_   sneaker_  inventory_ logistics_                        │
│  agent        agent     agent      agent                             │
│    │            │          │          │                               │
│    │  (budget   │ (LLM     │ (LLM     │ (catalog                     │
│    │   lookup)  │  picks)  │  summary │  lookup)                     │
│    │            │          │  + route)│                               │
│    └────────────┘          └──────────┘                               │
│                                                                       │
│   Shared AgentState (TypedDict) travels through every node:          │
│     input, user_name, next, output, budget,                          │
│     proposed_sneakers, sneaker_collection                            │
└───────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────────────┐
│                          Eval Harness                                 │
│                                                                       │
│   eval_runner.py  ──→  evals/runner.py  ──→  evals/scorers.py       │
│                              │                                        │
│                    app.stream() captures:                             │
│                      • nodes_visited  (routing path)                 │
│                      • node_outputs   (per-agent state updates)      │
│                      • node_latencies (per-agent wall-clock time)    │
│                      • final_state    (merged end state)             │
│                              │                                        │
│                    Scored on 6 dimensions:                            │
│                      1. Routing Accuracy                             │
│                      2. Budget Accuracy                              │
│                      3. Sneaker Validity (hallucination check)       │
│                      4. Budget Compliance                            │
│                      5. Failure Handling                             │
│                      6. Latency                                      │
│                              │                                        │
│                    evals/report.py  ──→  stdout report              │
└───────────────────────────────────────────────────────────────────────┘
```

---

## Agent Routing Paths

```
orchestrator
    │
    ├── financial_agent  (buying / shopping intent)
    │       │
    │       └── sneaker_agent  (LLM picks 2-3 sneakers within budget)
    │                │
    │                └── logistics_agent  (checks stock + market value)  ──→ END
    │
    ├── sneaker_agent  (style advice only, no budget needed)
    │       │
    │       └── logistics_agent ──→ END
    │
    ├── inventory_agent  (what sneakers do I own?)
    │       │
    │       ├── END  (user only wanted collection info)
    │       │
    │       └── financial_agent  (user also wants to shop)
    │                └── ... (same chain as above)
    │
    └── logistics_agent  (specific item stock check)  ──→ END
```

---

## Data Flow

```
data/catalog.py
    ├── USER_BUDGETS          ──→  financial_agent  ──→  state["budget"]
    ├── USER_SNEAKER_COLLECTION ──→ inventory_agent ──→  state["sneaker_collection"]
    └── SNEAKER_CATALOG       ──→  sneaker_agent   ──→  state["proposed_sneakers"]
                              ──→  logistics_agent  ──→  state["output"] (availability report)
```

---

## File Structure

```
sneaker-agent/
├── main.py                  Entry point — runs 3 hardcoded demo scenarios
├── eval_runner.py           CLI entry point for the eval harness
├── graph.py                 build_graph() — wires all agents into LangGraph
├── orchestrator.py          orchestrator() + router() — LLM routing logic
├── state.py                 AgentState TypedDict — shared across all agents
├── llm.py                   Shared Gemini Flash LLM instance
│
├── agents/
│   ├── financial_agent.py   Looks up user budget from catalog
│   ├── sneaker_agent.py     LLM picks 2-3 sneakers within budget
│   ├── inventory_agent.py   Reviews collection; routes to shop or stop
│   └── logistics_agent.py   Checks stock, retail vs market price, StockX link
│
├── data/
│   └── catalog.py           USER_BUDGETS, USER_SNEAKER_COLLECTION, SNEAKER_CATALOG
│
├── evals/
│   ├── cases.py             8 test case definitions with expected outcomes
│   ├── scorers.py           6 scoring functions (one per eval dimension)
│   ├── runner.py            Streams test cases through graph, collects results
│   └── report.py            Formats and prints the scored eval report
│
├── architecture/
│   └── diagram.md           This file
│
├── test_cases.md            Test case documentation with edge cases noted
└── README.md                Setup, usage, and architecture summary
```

---

## Technology Choices

| Component | Technology | Why |
|---|---|---|
| Agent orchestration | LangGraph | Native state graph with conditional routing; clear separation of nodes and edges |
| LLM | Gemini Flash (gemini-2.5-flash) | Fast and cost-effective for short structured prompts; temperature=0 for consistency |
| Eval streaming | LangGraph `stream_mode="updates"` | Yields per-node state deltas so the harness can capture routing, outputs, and timing without modifying agent code |
| State management | TypedDict (AgentState) | Type-safe shared state that LangGraph merges across nodes |
| Data | Static dict (catalog.py) | In a production system this would be a database; static data keeps the demo self-contained |
