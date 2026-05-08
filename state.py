from typing import TypedDict


class AgentState(TypedDict):
    """
    AgentState
    ----------
    The shared data container that travels through the entire LangGraph.
    Every agent receives this, reads the fields it needs, and returns a dict
    with only the fields it updated. LangGraph merges that dict back in.

    Fields:
        input              (str):   the original user question — never modified after start
        user_name          (str):   which user is asking — never modified after start
        next               (str):   which agent to run next; every agent must set this
        output             (str):   the human-readable result produced by the last agent
        budget             (float): set by financial_agent; how much the user can spend
        proposed_sneakers  (list):  set by sneaker_agent; sneaker names chosen within budget
        sneaker_collection (list):  set by inventory_agent; sneakers the user already owns
    """
    input:              str
    user_name:          str
    next:               str
    output:             str
    budget:             float
    proposed_sneakers:  list
    sneaker_collection: list
