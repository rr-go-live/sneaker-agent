from langgraph.graph import StateGraph, END

from state import AgentState
from orchestrator import orchestrator, router
from agents import (
    financial_agent,
    sneaker_agent,
    inventory_agent,
    logistics_agent,
    critique_agent,
)


def build_graph():
    """
    build_graph
    -----------
    Constructs and compiles the LangGraph agent graph.

    Flow:
      orchestrator → financial_agent | inventory_agent | sneaker_agent | logistics_agent
      financial_agent  → sneaker_agent
      inventory_agent  → financial_agent | END
      sneaker_agent    → critique_agent
      critique_agent   → logistics_agent (approved / max retries reached)
                       → sneaker_agent   (rejected, retry available)
      logistics_agent  → END

    The critique ↔ sneaker loop runs at most MAX_CRITIQUE_ATTEMPTS times
    (enforced inside critique_agent) before force-approving.

    Args:
        None

    Returns:
        CompiledGraph: a runnable LangGraph app ready to accept .stream() calls
    """
    graph = StateGraph(AgentState)

    graph.add_node("orchestrator",    orchestrator)
    graph.add_node("financial_agent", financial_agent)
    graph.add_node("sneaker_agent",   sneaker_agent)
    graph.add_node("inventory_agent", inventory_agent)
    graph.add_node("critique_agent",  critique_agent)
    graph.add_node("logistics_agent", logistics_agent)

    graph.set_entry_point("orchestrator")

    graph.add_conditional_edges(
        "orchestrator",
        router,
        {
            "financial_agent":  "financial_agent",
            "sneaker_agent":    "sneaker_agent",
            "inventory_agent":  "inventory_agent",
            "logistics_agent":  "logistics_agent",
        },
    )

    graph.add_conditional_edges(
        "financial_agent",
        router,
        {
            "sneaker_agent":    "sneaker_agent",
            "inventory_agent":  "inventory_agent",
            "logistics_agent":  "logistics_agent",
            END: END,
        },
    )

    graph.add_conditional_edges(
        "inventory_agent",
        router,
        {
            "financial_agent":  "financial_agent",
            "sneaker_agent":    "sneaker_agent",
            END: END,
        },
    )

    # sneaker_agent always hands off to critique_agent
    graph.add_conditional_edges(
        "sneaker_agent",
        router,
        {
            "critique_agent":   "critique_agent",
            # keep legacy routes so eval cases that still set next=logistics_agent work
            "logistics_agent":  "logistics_agent",
            END: END,
        },
    )

    # critique_agent either approves (→ logistics) or rejects (→ sneaker retry)
    graph.add_conditional_edges(
        "critique_agent",
        router,
        {
            "logistics_agent":  "logistics_agent",
            "sneaker_agent":    "sneaker_agent",
            END: END,
        },
    )

    graph.add_conditional_edges(
        "logistics_agent",
        router,
        {END: END},
    )

    return graph.compile()
