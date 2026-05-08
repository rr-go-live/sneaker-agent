from langgraph.graph import StateGraph, END

from state import AgentState
from orchestrator import orchestrator, router
from agents import financial_agent, sneaker_agent, inventory_agent, logistics_agent


def build_graph():
    """
    build_graph
    -----------
    Constructs and compiles the LangGraph agent graph.

    The graph is a flowchart where nodes are agents and conditional edges
    let the router() function decide which agent runs next based on the
    'next' field each agent writes to the shared state.

    Args:
        None

    Returns:
        CompiledGraph: a runnable LangGraph app ready to accept .invoke() calls
    """
    graph = StateGraph(AgentState)

    # Register all agents as nodes
    graph.add_node("orchestrator",    orchestrator)
    graph.add_node("financial_agent", financial_agent)
    graph.add_node("sneaker_agent",   sneaker_agent)
    graph.add_node("inventory_agent", inventory_agent)
    graph.add_node("logistics_agent", logistics_agent)

    # Every run starts at the orchestrator
    graph.set_entry_point("orchestrator")

    # After orchestrator: go to whichever agent the LLM picked
    graph.add_conditional_edges(
        "orchestrator",
        router,
        {
            "financial_agent": "financial_agent",
            "sneaker_agent":   "sneaker_agent",
            "inventory_agent": "inventory_agent",
            "logistics_agent": "logistics_agent",
        },
    )

    # After financial_agent: goes to sneaker_agent, or stops if no budget found
    graph.add_conditional_edges(
        "financial_agent",
        router,
        {
            "sneaker_agent":   "sneaker_agent",
            "inventory_agent": "inventory_agent",
            "logistics_agent": "logistics_agent",
            END: END,
        },
    )

    # After sneaker_agent: always goes to logistics_agent to check availability
    graph.add_conditional_edges(
        "sneaker_agent",
        router,
        {
            "financial_agent": "financial_agent",
            "inventory_agent": "inventory_agent",
            "logistics_agent": "logistics_agent",
            END: END,
        },
    )

    # After inventory_agent: stops, or hands off to financial_agent to shop
    graph.add_conditional_edges(
        "inventory_agent",
        router,
        {
            "sneaker_agent":   "sneaker_agent",
            "financial_agent": "financial_agent",
            END: END,
        },
    )

    # After logistics_agent: always stops — it is the last step
    graph.add_conditional_edges(
        "logistics_agent",
        router,
        {END: END},
    )

    return graph.compile()
