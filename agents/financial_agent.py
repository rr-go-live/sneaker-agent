from langgraph.graph import END

from data.catalog import USER_BUDGETS
from database import get_user_budget


def financial_agent(state):
    """
    financial_agent
    ---------------
    Resolves the user's budget and routes to sneaker_agent.

    Resolution priority:
      1. Web path  — budget already in state (set by the API from the UI form).
      2. DB path   — looks up by user_name in the SQLite users table.
      3. CLI path  — falls back to USER_BUDGETS dict (eval / main.py only).
      4. No budget found → ends flow with an error message.

    Args:
        state (AgentState): reads 'budget' (optional) and 'user_name'

    Returns:
        dict: updates 'budget', 'output', 'next', 'reasoning'
    """
    # Web path: budget was passed in from the UI form
    pre_set_budget = state.get("budget")
    if pre_set_budget is not None and pre_set_budget > 0:
        return {
            "budget": pre_set_budget,
            "output": f"Budget confirmed: ${pre_set_budget:.2f}",
            "next":   "sneaker_agent",
            "reasoning": (
                f"Using the ${pre_set_budget:.2f} budget supplied directly from the "
                "request, so no lookup is needed. Handing off to the sneaker agent "
                "to find picks that fit."
            ),
        }

    user_name = state.get("user_name", "")

    # DB path: look up stored budget from SQLite
    db_budget = get_user_budget(user_name)
    if db_budget is not None:
        return {
            "budget": db_budget,
            "output": f"Budget confirmed: ${db_budget:.2f}",
            "next":   "sneaker_agent",
            "reasoning": (
                f"No budget was provided, so I looked up '{user_name}' in the "
                f"database and found a saved budget of ${db_budget:.2f}."
            ),
        }

    # CLI fallback
    budget = USER_BUDGETS.get(user_name)
    if budget is None:
        return {
            "output": f"Sorry, no budget found for user '{user_name}'.",
            "next":   END,
            "reasoning": (
                f"Could not resolve a budget for '{user_name}' from the request, "
                "the database, or the fallback table, so the pipeline cannot "
                "continue without one."
            ),
        }

    return {
        "budget": budget,
        "output": f"Budget confirmed: ${budget:.2f}",
        "next":   "sneaker_agent",
        "reasoning": (
            f"Fell back to the built-in budget table for '{user_name}' and found "
            f"${budget:.2f}."
        ),
    }
