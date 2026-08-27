import re

from langchain_core.messages import HumanMessage

from llm import llm
from reasoning import split_reasoning_answer

# Phrases that reference the user's EXISTING collection. Matching any of
# these deterministically routes to inventory_agent, bypassing the LLM
# routing call entirely.
#
# This exists because the LLM router reliably mis-routes a compound request
# like "what do I already own, and what new heat can I cop to complete the
# rotation?" — the shopping language ("new heat", "cop", "complete the
# rotation") dominates its judgment and it picks sneaker_agent every time,
# skipping inventory_agent completely, even though the message plainly asks
# about the existing collection too. Confirmed non-flaky: the same input
# misrouted 5/5 runs, so this isn't LLM temperature noise to route around —
# the prompt gives the model no rule for handling both intents in one
# message, and its own agent description calls sneaker_agent "the default
# for anything sneaker-related," which actively biases it away from
# inventory_agent whenever shopping language is present at all.
#
# A false positive is safe: inventory_agent runs its own second LLM check
# ("does the user also want to buy?") and hands off to sneaker_agent when
# it detects shopping intent — so a compound request that lands here still
# reaches sneaker_agent, just via inventory_agent first, which is the
# behavior the graph already supports (agents/inventory_agent.py) and the
# behavior TC-003 expects.
#
# Deliberately narrower than "mentions the word collection" — "add to my
# collection" and "new heat for my collection" both use that word but are
# pure shopping requests, not a check of what's already owned. Each
# alternative below requires a checking/viewing verb, not just the noun.
_COLLECTION_REFERENCE_PATTERN = re.compile(
    r"""
    \b(?:
        what\s+(?:do\s+)?i\s+(?:already\s+)?(?:own|have|got)
        | what\s+i\s+(?:already\s+)?(?:own|have)
        | already\s+(?:own|have)
        | (?:see|check|show|view|browse|look\s+at)\s+(?:my|the)\s+(?:current\s+|existing\s+)?collection
        | what(?:'s|\s+is)\s+in\s+(?:my|the)\s+collection
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _mentions_existing_collection(text):
    """
    _mentions_existing_collection
    -------------------------------
    Deterministic check for language referencing the user's existing
    sneaker collection ("what do I already own", "my collection", etc.).

    Args:
        text (str): the user's free-text input

    Returns:
        bool: True when the text references the existing collection
    """
    if not text:
        return False
    return bool(_COLLECTION_REFERENCE_PATTERN.search(text))


def orchestrator(state):
    """
    orchestrator
    ------------
    The first node that runs on every request. Routes to one of three
    agents — deterministically when the request references the user's
    existing collection, via an LLM call otherwise.

    The three agents it can route to:
      - inventory_agent  → user wants to know what sneakers they already own
                           (also the entry point for a compound request that
                           ALSO wants new picks — inventory_agent hands off
                           to sneaker_agent itself once it detects that)
      - sneaker_agent    → user wants recommendations, style/trend advice, or
                           to add to their collection — anything sneaker-related
                           that isn't specifically about their existing
                           collection or a named item's stock status
      - logistics_agent  → user asks if a specific named sneaker is in stock

    A guardrail ensures only recognised agent names are accepted. Unknown
    LLM answers fall back to sneaker_agent.

    Args:
        state (AgentState): reads 'input'

    Returns:
        dict: sets 'next' to the name of the first agent to run, plus
              'reasoning' explaining why that agent was chosen
    """
    user_input = state["input"]

    # Deterministic pre-check: collection language always wins, no LLM call
    # needed. See _COLLECTION_REFERENCE_PATTERN above for why this exists.
    if _mentions_existing_collection(user_input):
        return {
            "next": "inventory_agent",
            "reasoning": (
                "The request references the existing collection (e.g. "
                "\"what do I own\"/\"my collection\"), so this routes to "
                "inventory_agent regardless of any shopping language also "
                "present — inventory_agent will hand off to sneaker_agent "
                "itself if it detects the user also wants to buy."
            ),
        }

    decision = llm.invoke([
        HumanMessage(content=f"""
You are a sneaker shopping assistant orchestrator. Pick which agent should handle the user's request.

Agents:
- sneaker_agent    → user wants recommendations, style/trend advice, or to add
                     to their collection (the default for anything sneaker-related)
- inventory_agent  → user wants to know what sneakers they already own
- logistics_agent  → user asks if a specific named sneaker is currently available in the store

User input: {user_input}

Respond in EXACTLY this format:
REASONING: <2-3 sentences explaining which intent you detected in the user's
message and why it maps to the agent you chose>
ANSWER: <one of: sneaker_agent, inventory_agent, logistics_agent>
""")
    ])

    reasoning, answer = split_reasoning_answer(decision.content)
    llm_answer = answer.lower()

    if "inventory_agent" in llm_answer:
        next_step = "inventory_agent"
    elif "logistics_agent" in llm_answer:
        next_step = "logistics_agent"
    else:
        next_step = "sneaker_agent"

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
