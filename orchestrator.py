from langchain_core.messages import HumanMessage

from llm import llm


def orchestrator(state):
    """
    orchestrator
    ------------
    The first node that runs on every request. Uses the LLM to read the user's
    message and decide which agent should handle it.

    The four agents it can route to:
      - financial_agent  → user wants to buy sneakers or add to their collection
      - sneaker_agent    → user wants style/trend advice only, no buying intent
      - inventory_agent  → user wants to know what sneakers they already own
      - logistics_agent  → user asks if a specific named sneaker is in stock

    A guardrail ensures only recognised agent names are accepted. Unknown answers
    fall back to financial_agent.

    Args:
        state (AgentState): reads 'input'

    Returns:
        dict: sets 'next' to the name of the first agent to run
    """
    print("\n[orchestrator] User input received: " + state["input"])
    print("[orchestrator] Asking LLM which agent should handle this...")

    user_input = state["input"]

    decision = llm.invoke([
        HumanMessage(content=f"""
You are a sneaker shopping assistant orchestrator. Pick which agent should handle the user's request.

Agents:
- financial_agent  → user wants to buy sneakers, get recommendations, or add to their collection
                     (always use this first when there is any buying or shopping intent)
- sneaker_agent    → user ONLY wants style or trend advice with no intent to purchase
- inventory_agent  → user wants to know what sneakers they already own
- logistics_agent  → user asks if a specific named sneaker is currently available in the store

User input: {user_input}

Return ONLY one of these four exact strings:
financial_agent, sneaker_agent, inventory_agent, logistics_agent
""")
    ])

    llm_answer = decision.content.strip().lower()
    print(f"[orchestrator] LLM chose: '{llm_answer}'")

    # Guardrail — only route to known agent names
    if "financial_agent" in llm_answer:
        next_step = "financial_agent"
    elif "inventory_agent" in llm_answer:
        next_step = "inventory_agent"
    elif "logistics_agent" in llm_answer:
        next_step = "logistics_agent"
    elif "sneaker_agent" in llm_answer:
        next_step = "sneaker_agent"
    else:
        print("[orchestrator] Did not recognise LLM answer — defaulting to financial_agent.")
        next_step = "financial_agent"

    print(f"[orchestrator] Routing to: {next_step}")
    return {"next": next_step}


def router(state):
    """
    router
    ------
    Reads the 'next' field that each agent writes to the state.
    LangGraph calls this after every node to decide where to go next.

    Args:
        state (AgentState): reads 'next'

    Returns:
        str: the name of the next node to run, or END to stop
    """
    return state["next"]
