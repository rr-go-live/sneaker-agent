# Specs

Technical specification for Sneaker Agent — a multi-agent LLM system that takes a
shopper's request in plain English and returns a validated, in-stock set of sneaker
picks with live pricing.

These documents describe what the system does, how it is built, and why each design
choice was made. They are written to be read in order, but each one stands on its own.

| Doc | What it covers |
| --- | --- |
| [00-overview.md](00-overview.md) | What the product is, who it serves, scope boundaries, and the business case |
| [01-core-functionality.md](01-core-functionality.md) | Every user-facing flow and the behavior rules each agent follows |
| [02-ai-ml-design.md](02-ai-ml-design.md) | Agent orchestration, prompt contracts, hallucination guardrails, model selection, cost |
| [03-api-and-services.md](03-api-and-services.md) | Endpoint contracts, streaming protocol, auth, service boundaries, and the path to real microservices |
| [04-data-schema.md](04-data-schema.md) | Catalog schema, database tables, agent state, and every wire payload |
| [05-evaluation.md](05-evaluation.md) | The eval harness: dimensions, scoring math, current results, and what the numbers mean |

## Status

This is a working local build, not a deployed product. Every doc includes a section
on what the design would mean in production — what it protects against, what it
would cost, and what would have to change before real traffic hit it.

## Reading the code alongside

| Concept in these docs | Where it lives |
| --- | --- |
| Agent graph wiring | [graph.py](../graph.py) |
| Routing | [orchestrator.py](../orchestrator.py) |
| Shared state contract | [state.py](../state.py) |
| Deterministic filtering | [agents/selection.py](../agents/selection.py) |
| HTTP surface | [api.py](../api.py) |
| Persistence | [database.py](../database.py) |
| Eval harness | [evals/](../evals/) |
