from langchain_core.messages import HumanMessage
from langgraph.graph import END

from data.catalog import SNEAKER_CATALOG
from llm import llm
from reasoning import split_reasoning_answer
from agents.selection import DEFAULT_PICK_COUNT

# After this many rejections the critique agent force-approves to avoid
# an infinite loop. The user still gets reviewed picks, just not perfect ones.
MAX_CRITIQUE_ATTEMPTS = 2


def critique_agent(state):
    """
    critique_agent
    --------------
    Reviews the sneaker_agent's proposed picks and either approves them
    (→ logistics_agent) or rejects with specific feedback (→ sneaker_agent
    for one retry, up to MAX_CRITIQUE_ATTEMPTS).

    Two deterministic checks run first, before any LLM call, because they
    are facts rather than judgment calls:
      - COUNT:  proposed picks must match requested_count exactly
      - BRAND:  every pick must be one of requested_brands, when specified
                (sneaker_agent already hard-filters for this — this is a
                defense-in-depth safety net, not the primary enforcement)

    There is no budget check — the app has no price ceiling. Retail/market
    price still flows through to the user as reference data (via
    logistics_agent), it just isn't a pass/fail criterion here.

    If both deterministic checks pass, two rubrics are evaluated by the LLM:
      1. Value           — at least one pick should have market_value > retail
      2. Brand diversity — picks should not all be the same brand, UNLESS
                           the user specifically requested a single brand,
                           in which case diversity is not a defect and this
                           rubric is dropped entirely

    Market data from SNEAKER_CATALOG (last_sale, lowest_ask, deadstock_sold)
    is included in the prompt so the LLM can reason about real numbers.

    Force-approves after MAX_CRITIQUE_ATTEMPTS to break out of any retry loop.

    Args:
        state (AgentState): reads 'proposed_sneakers', 'sneaker_collection',
                            'critique_attempts', 'requested_brands',
                            'requested_count'

    Returns:
        dict: updates 'critique_feedback', 'critique_attempts', 'output',
              'next', 'reasoning'
    """
    proposed          = state.get("proposed_sneakers") or []
    wardrobe          = state.get("sneaker_collection") or []
    attempts          = state.get("critique_attempts") or 0
    requested_brands  = state.get("requested_brands") or []
    requested_count   = state.get("requested_count") or DEFAULT_PICK_COUNT

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
            "critique_feedback": f"No sneakers were proposed. Please select exactly {requested_count}.",
            "output": "No picks to critique — requesting retry.",
            "next":   "sneaker_agent",
            "reasoning": (
                "The sneaker agent returned no picks, so there is nothing to "
                f"evaluate. Sending it back to select exactly {requested_count}."
            ),
        }

    # ── Deterministic checks — facts, not judgment calls ─────────────────────
    if len(proposed) != requested_count:
        return {
            "critique_attempts": attempts + 1,
            "critique_feedback": (
                f"You proposed {len(proposed)} sneaker(s) but exactly "
                f"{requested_count} were requested. Pick exactly {requested_count}."
            ),
            "output": f"Rejected: {len(proposed)} picks, expected {requested_count}.",
            "next":   "sneaker_agent",
            "reasoning": (
                f"Proposed count ({len(proposed)}) doesn't match the requested "
                f"count ({requested_count}) — this is a hard requirement, not "
                "a style judgment, so sending it back for an exact retry."
            ),
        }

    if requested_brands:
        wanted = {b.lower() for b in requested_brands}
        off_brand = [
            name for name in proposed
            if SNEAKER_CATALOG.get(name, {}).get("brand", "").lower() not in wanted
        ]
        if off_brand:
            return {
                "critique_attempts": attempts + 1,
                "critique_feedback": (
                    f"These picks aren't from the requested brand(s) "
                    f"({', '.join(requested_brands)}): {', '.join(off_brand)}. "
                    "Only propose sneakers from the requested brand(s)."
                ),
                "output": f"Rejected: off-brand picks {off_brand}",
                "next":   "sneaker_agent",
                "reasoning": (
                    f"Found pick(s) outside the requested brand(s) "
                    f"{requested_brands}: {off_brand}. Brand compliance is a "
                    "hard requirement, so sending it back for a corrected retry."
                ),
            }

    # ── Enrich picks with market data for the LLM ────────────────────────────
    pick_lines = []

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

        pick_lines.append(
            f"  - {name} | {brand} | retail ${retail} | market ${market}"
            f" | last sale ${last} | lowest ask ${ask} | {sold:,} total sold"
        )

    picks_text  = "\n".join(pick_lines)
    wardrobe_text = ", ".join(wardrobe) if wardrobe else "none"

    # DIVERSITY only makes sense as a rubric when the user didn't ask for a
    # specific brand — otherwise a single-brand result is exactly correct,
    # not a defect, and penalizing it would fight the user's own request.
    if requested_brands:
        rubric_block = """1. VALUE: At least one pick should have a market value above retail price
          (market value > retail price means it appreciates — a smart buy)."""
        rubric_note = (
            f"Note: the user specifically requested {', '.join(requested_brands)}, "
            "so all picks being that brand is correct and should NOT be treated "
            "as a lack of diversity."
        )
    else:
        rubric_block = """1. VALUE: At least one pick should have a market value above retail price
          (market value > retail price means it appreciates — a smart buy).
2. DIVERSITY: Picks should not all come from the same brand."""
        rubric_note = ""

    response = llm.invoke([
        HumanMessage(content=f"""
You are a sneaker buying advisor reviewing proposed sneaker picks. There is no
budget to check — the retail/market prices below are reference data only.

User already owns: {wardrobe_text}

Proposed picks:
{picks_text}

Evaluate the picks against these rubrics:

{rubric_block}
{rubric_note}

Respond in EXACTLY this format:
REASONING: <2-3 sentences walking through each rubric with the actual numbers —
whether any pick appreciates, and brand spread>
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
