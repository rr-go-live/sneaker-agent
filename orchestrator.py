from langchain_core.messages import HumanMessage

from llm import llm
from reasoning import split_reasoning_answer


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
        dict: sets 'next' to the name of the first agent to run, plus
              'reasoning' explaining why that agent was chosen
    """
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

Respond in EXACTLY this format:
REASONING: <2-3 sentences explaining which intent you detected in the user's
message and why it maps to the agent you chose>
ANSWER: <one of: financial_agent, sneaker_agent, inventory_agent, logistics_agent>
""")
    ])

    reasoning, answer = split_reasoning_answer(decision.content)
    llm_answer = answer.lower()

    if "financial_agent" in llm_answer:
        next_step = "financial_agent"
    elif "inventory_agent" in llm_answer:
        next_step = "inventory_agent"
    elif "logistics_agent" in llm_answer:
        next_step = "logistics_agent"
    elif "sneaker_agent" in llm_answer:
        next_step = "sneaker_agent"
    else:
        next_step = "financial_agent"

    return {"next": next_step, "reasoning": reasoning}


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
