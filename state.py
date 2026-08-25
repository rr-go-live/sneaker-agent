from typing import Optional, TypedDict


class AgentState(TypedDict):
    """
    AgentState
    ----------
    The shared data container that travels through the entire LangGraph.
    Every agent receives this, reads the fields it needs, and returns a dict
    with only the fields it updated. LangGraph merges that dict back in.

    Fields:
        input              (str):          the original user question
        user_name          (str):          which user is asking
        next               (str):          which agent to run next
        output             (str):          human-readable result of the last agent
        proposed_sneakers  (list[str]):    set by sneaker_agent
        sneaker_collection (list[str]):    set by inventory_agent
        critique_feedback  (str|None):     rejection reason from critique_agent;
                                           injected into sneaker_agent on retry
        critique_attempts  (int):          number of critique cycles completed;
                                           capped at MAX_CRITIQUE_ATTEMPTS in critique_agent
        reasoning          (str|None):     plain-English explanation of WHY the
                                           agent that just ran made its decision;
                                           streamed to the UI logging panel so the
                                           user can follow the LLM's logic
        requested_brands   (list[str]):    brand filter selected in the UI, e.g.
                                           ["Jordan"]; hard-filtered in
                                           sneaker_agent, not left to the LLM
        requested_colors   (list[str]):    colorway filter selected in the UI
        requested_count    (int|None):     explicit pick count parsed from the
                                           request; None lets sneaker_agent use
                                           its own default
    """
    input:              str
    user_name:          str
    next:               str
    output:             str
    proposed_sneakers:  list
    sneaker_collection: list
    critique_feedback:  Optional[str]
    critique_attempts:  int
    reasoning:          Optional[str]
    requested_brands:   list
    requested_colors:   list
    requested_count:    Optional[int]
