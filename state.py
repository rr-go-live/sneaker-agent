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
        requested_brands   (list[str]):    brand filter, e.g. ["Jordan"]. Set
                                           from the UI's brand chips, or parsed
                                           out of free text by sneaker_agent
                                           when no chip was selected; either way
                                           it is hard-filtered in sneaker_agent
                                           rather than left to the LLM.
                                           sneaker_agent writes the resolved
                                           value back so critique_agent enforces
                                           the same brand rule.
        requested_colors   (list[str]):    colorway filter, resolved the same way
        requested_profile  (str|None):     silhouette filter — "low", "mid", or
                                           "high"; resolved the same way
        requested_count    (int|None):     explicit pick count parsed from the
                                           request; None lets sneaker_agent use
                                           its own default
        availability       (list|None):    structured stock rows from
                                           logistics_agent — one dict per pick
                                           with name, brand, in_stock, quantity,
                                           retail, market and link. The web UI
                                           renders these as a table; 'output'
                                           carries the same data as plain text
                                           for the CLI and eval report.
        retail_total       (float|None):   summed retail price of the picks
        no_matches         (bool|None):    set by sneaker_agent when nothing in
                                           the catalog satisfies the stated
                                           constraints. Tells critique_agent to
                                           skip its retry loop — a retry cannot
                                           conjure a match — and to preserve the
                                           explanation of which filters failed

    Price ceilings and release-year floors are parsed per-request inside
    sneaker_agent rather than carried here, since nothing downstream needs to
    re-check them — the candidate pool physically cannot contain a violation.
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
    requested_profile:  Optional[str]
    requested_count:    Optional[int]
    availability:       Optional[list]
    retail_total:       Optional[float]
    no_matches:         Optional[bool]
