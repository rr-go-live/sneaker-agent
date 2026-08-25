from langchain_core.messages import HumanMessage

from data.catalog import SNEAKER_CATALOG
from database import get_out_of_stock_names
from llm import llm
from reasoning import split_reasoning_answer
from agents.selection import (
    filter_by_brand, filter_by_color, extract_requested_count, extract_proposed_names,
    clamp_count_to_pool, DEFAULT_PICK_COUNT,
)

# Max catalog rows sent to the LLM — keeps prompt size manageable
# while still giving good variety (1 668 total sneakers in catalog).
MAX_CATALOG_SIZE = 80


def sneaker_agent(state):
    """
    sneaker_agent
    -------------
    Picks sneakers from the catalog matching the requested brand(s)/color(s)
    and pick count. There is no budget/price ceiling — a user can search for
    and add any sneaker regardless of cost; retail/market price is still
    shown on every pick as reference data, just never used to filter.

    Compliance is enforced deterministically rather than left to prompt
    wording, since an LLM can silently ignore or contradict a soft
    instruction:
      1. Drop anything out of stock
      2. Hard-filter to the requested brand(s), if any (brand data is
         always present, so this is an exact filter — a request for a
         brand with zero matches correctly yields no picks instead of
         silently substituting a different brand)
      3. Prefer the requested color(s), if any (colorway data is often
         missing, so this falls back to the full pool rather than an
         empty result — but the LLM is told plainly whether a real
         color match was found)
      4. Sort by sales_this_period descending (popularity proxy) and cap
         at MAX_CATALOG_SIZE
      5. After the LLM answers, keep only names that were actually in the
         candidate pool shown to it — guards against a hallucinated pick
         bypassing every filter above

    The requested pick count is parsed from the free-text input (e.g. "just
    2 options"); DEFAULT_PICK_COUNT is used when none is stated.

    If critique_feedback is present in state (retry after rejection), the
    feedback is included in the prompt so the LLM can correct its picks.

    Args:
        state (AgentState): reads 'input', 'critique_feedback',
                            'requested_brands', 'requested_colors'

    Returns:
        dict: updates 'proposed_sneakers', 'output', 'next', 'reasoning'
    """
    user_input        = state.get("input", "")
    critique_feedback = state.get("critique_feedback")
    requested_brands  = state.get("requested_brands") or []
    requested_colors  = state.get("requested_colors") or []
    requested_count   = extract_requested_count(user_input, default=DEFAULT_PICK_COUNT)

    # ── Filter: in stock ──────────────────────────────────────────────────────
    out_of_stock = get_out_of_stock_names()

    candidates = [
        (name, details)
        for name, details in SNEAKER_CATALOG.items()
        if name not in out_of_stock
    ]

    # ── Hard-filter brand, soft-prefer color ─────────────────────────────────
    candidates = filter_by_brand(candidates, requested_brands)
    candidates, color_matched = filter_by_color(candidates, requested_colors)

    candidates.sort(
        key=lambda x: x[1].get("sales_this_period", 0),
        reverse=True,
    )

    candidates = candidates[:MAX_CATALOG_SIZE]

    if not candidates:
        return {
            "proposed_sneakers": [],
            "output": "No sneakers matched the requested brand.",
            "next":   "critique_agent",
            "requested_count": requested_count,
            "reasoning": (
                f"No in-stock catalog entries matched brand(s) {requested_brands or 'any'}, "
                "so there is nothing to propose."
            ),
        }

    original_count  = requested_count
    requested_count = clamp_count_to_pool(requested_count, len(candidates))
    count_clamp_note = ""
    if requested_count < original_count:
        count_clamp_note = (
            f"\nNote: only {len(candidates)} sneaker(s) matched the brand/color "
            f"filters, so pick {requested_count} instead of the originally requested "
            f"{original_count} — do not repeat any name."
        )

    catalog_lines = []
    for name, d in candidates:
        catalog_lines.append(
            f"  - {name} | {d['brand']} | {d.get('colorway', 'unknown colorway')}"
            f" | ${d['retail_price']} retail | ${d.get('market_value', 0)} market"
            f" | {d.get('profile', '?')}-top"
        )

    catalog_text = "\n".join(catalog_lines)

    # ── Inject critique feedback on retry ────────────────────────────────────
    feedback_block = ""
    if critique_feedback:
        feedback_block = f"""
A previous selection was rejected. Reason:
{critique_feedback}

Address those issues in your new selection.
"""

    color_note = ""
    if requested_colors and not color_matched:
        color_note = (
            f"\nNote: no candidate has a confirmed {'/'.join(requested_colors)} colorway in "
            "the data below, so pick the closest style match and say so in your reasoning."
        )

    brand_instruction = (
        f"Every option below already matches the requested brand(s): {', '.join(requested_brands)}."
        if requested_brands else
        "No specific brand was requested — favor variety across brands."
    )

    response = llm.invoke([
        HumanMessage(content=f"""
You are a sneaker expert and stylist. There is no budget constraint — pick based
purely on style fit, not price. Retail/market price is shown for reference only.

Available sneakers (name | brand | colorway | retail | market value | profile):
{catalog_text}
{feedback_block}
User request: {user_input}

{brand_instruction}{color_note}{count_clamp_note}

Pick EXACTLY {requested_count} sneaker{'s' if requested_count != 1 else ''} from the list above
that match the user's style. Do not pick more or fewer than {requested_count}.

Respond in EXACTLY this format:
REASONING: <2-3 sentences explaining how these picks fit the user's style
preferences. If correcting after rejection, say what you changed>
ANSWER: <comma-separated list of exactly {requested_count} sneaker name(s) spelled
exactly as shown>

Example:
REASONING: Both lean toward the low-top, neutral look the user asked for.
ANSWER: Jordan 4 Retro SB Pine Green, Nike Dunk Low Retro White Black
""")
    ])

    reasoning, answer = split_reasoning_answer(response.content)
    proposed_sneakers = extract_proposed_names(answer, candidates)

    return {
        "proposed_sneakers": proposed_sneakers,
        "output":  "Sneaker recommendations: " + ", ".join(proposed_sneakers),
        "next":    "critique_agent",
        "requested_count": requested_count,
        "reasoning": reasoning,
    }
