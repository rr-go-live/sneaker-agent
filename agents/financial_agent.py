from langgraph.graph import END

from data.catalog import USER_BUDGETS


def financial_agent(state):
    """
    financial_agent
    ---------------
    Looks up the user's budget from USER_BUDGETS.
    If a budget is found it saves it to state and routes to sneaker_agent.
    If no budget is found it ends the flow with an error message.

    Args:
        state (AgentState): reads 'user_name'

    Returns:
        dict: updates 'budget', 'output', and 'next'
    """
    print("\n[financial_agent] Running...")

    user_name = state.get("user_name", "John")
    budget = USER_BUDGETS.get(user_name)

    if budget is None:
        print(f"[financial_agent] No budget found for '{user_name}'.")
        return {
            "output": "Sorry, we could not find a budget for " + user_name + ".",
            "next": END,
        }

    print(f"[financial_agent] Found budget for {user_name}: ${budget:.2f}")
    print("[financial_agent] Passing budget to sneaker_agent...")

    return {
        "budget": budget,
        "output": "Budget for " + user_name + ": $" + str(budget),
        "next": "sneaker_agent",
    }
