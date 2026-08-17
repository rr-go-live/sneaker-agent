from langchain_core.messages import HumanMessage
from langgraph.graph import END

from data.catalog import SNEAKER_CATALOG
from llm import llm
from reasoning import split_reasoning_answer

# After this many rejections the critique agent force-approves to avoid
# an infinite loop. The user still gets reviewed picks, just not perfect ones.
MAX_CRITIQUE_ATTEMPTS = 2


def critique_agent(state):
    """
    critique_agent
    --------------
    Reviews the sneaker_agent's proposed picks against three rubrics and
    either approves them (→ logistics_agent) or rejects with specific
    feedback (→ sneaker_agent for one retry, up to MAX_CRITIQUE_ATTEMPTS).

    Rubrics evaluated by the LLM:
      1. Budget compliance  — total retail price must be ≤ budget
      2. Value              — at least one pick should have market_value > retail
      3. Brand diversity    — picks should not all be the same brand

    Market data from SNEAKER_CATALOG (last_sale, lowest_ask, deadstock_sold)
    is included in the prompt so the LLM can reason about real numbers.

    Force-approves after MAX_CRITIQUE_ATTEMPTS to break out of any retry loop.

    Args:
        state (AgentState): reads 'proposed_sneakers', 'budget',
                            'sneaker_collection', 'critique_attempts'

    Returns:
        dict: updates 'critique_feedback', 'critique_attempts', 'output',
              'next', 'reasoning'
    """
    proposed   = state.get("proposed_sneakers") or []
    budget     = state.get("budget") or 0
    wardrobe   = state.get("sneaker_collection") or []
    attempts   = state.get("critique_attempts") or 0

    # Force-approve if we've already retried enough
    if attempts >= MAX_CRITIQUE_ATTEMPTS:
        return {
            "critique_attempts": attempts,
            "critique_feedback": None,
            "output": "Picks approved after review.",
            "next":   "logistics_agent",
            "reasoning": (
                f"Reached the maximum of {MAX_CRITIQUE_ATTEMPTS} review cycles, "
                "so I'm approving the current picks to avoid an endless retry loop."
            ),
        }

    if not proposed:
        return {
            "critique_attempts": attempts + 1,
            "critique_feedback": "No sneakers were proposed. Please select 2-3 options.",
            "output": "No picks to critique — requesting retry.",
            "next":   "sneaker_agent",
            "reasoning": (
                "The sneaker agent returned no picks, so there is nothing to "
                "evaluate. Sending it back to select 2-3 options."
            ),
        }

    # ── Enrich picks with market data for the LLM ────────────────────────────
    pick_lines = []
    total_retail = 0.0

    for name in proposed:
        details = SNEAKER_CATALOG.get(name)
        if details is None:
            pick_lines.append(f"  - {name}: NOT FOUND in catalog")
            continue

        retail  = details.get("retail_price", 0)
        market  = details.get("market_value", 0)
        last    = details.get("last_sale", market)
        ask     = details.get("lowest_ask", market)
        sold    = details.get("deadstock_sold", 0)
        brand   = details.get("brand", "?")
        total_retail += retail

        pick_lines.append(
            f"  - {name} | {brand} | retail ${retail} | market ${market}"
            f" | last sale ${last} | lowest ask ${ask} | {sold:,} total sold"
        )

    picks_text  = "\n".join(pick_lines)
    wardrobe_text = ", ".join(wardrobe) if wardrobe else "none"

    response = llm.invoke([
        HumanMessage(content=f"""
You are a strict sneaker buying advisor reviewing proposed sneaker picks.

User budget: ${budget:.2f}
Total retail cost of picks: ${total_retail:.2f}
User already owns: {wardrobe_text}

Proposed picks:
{picks_text}

Evaluate the picks against these three rubrics:

1. BUDGET: Total retail must not exceed the user's budget.
2. VALUE:  At least one pick should have a market value above retail price
           (market value > retail price means it appreciates — a smart buy).
3. DIVERSITY: Picks should not all come from the same brand.

Respond in EXACTLY this format:
REASONING: <2-3 sentences walking through each rubric with the actual numbers —
the total retail vs budget, whether any pick appreciates, and brand spread>
ANSWER: APPROVED   (if all rubrics pass)
        or
ANSWER: REJECTED: <one concise sentence explaining what is wrong and what the
        sneaker agent should do differently>
""")
    ])

    reasoning, answer = split_reasoning_answer(response.content)
    answer = answer.strip()

    if answer.upper().startswith("APPROVED"):
        return {
            "critique_attempts": attempts + 1,
            "critique_feedback": None,
            "output": "Picks approved by critique agent.",
            "next":   "logistics_agent",
            "reasoning": reasoning,
        }

    # Rejected — extract the reason and send back for retry
    reason = answer.replace("REJECTED:", "").replace("rejected:", "").strip()

    return {
        "critique_attempts": attempts + 1,
        "critique_feedback": reason,
        "output": f"Critique rejected picks: {reason}",
        "next":   "sneaker_agent",
        "reasoning": reasoning or reason,
    }
