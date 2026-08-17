from langchain_core.messages import HumanMessage

from data.catalog import SNEAKER_CATALOG
from database import get_out_of_stock_names
from llm import llm
from reasoning import split_reasoning_answer

# Max catalog rows sent to the LLM — keeps prompt size manageable
# while still giving good variety (1 668 total sneakers in catalog).
MAX_CATALOG_SIZE = 80


def sneaker_agent(state):
    """
    sneaker_agent
    -------------
    Picks 2-3 sneakers from the catalog that fit the user's budget and style.

    Pre-filters the full catalog before passing to the LLM:
      1. Drops anything above budget
      2. Sorts by sales_this_period descending (popularity proxy)
      3. Caps at MAX_CATALOG_SIZE entries

    If critique_feedback is present in state (retry after rejection), the
    feedback is included in the prompt so the LLM can correct its picks.

    Args:
        state (AgentState): reads 'budget', 'input', 'critique_feedback'

    Returns:
        dict: updates 'proposed_sneakers', 'output', 'next', 'reasoning'
    """
    budget            = state.get("budget") or 500.0
    user_input        = state.get("input", "")
    critique_feedback = state.get("critique_feedback")

    # ── Filter: in budget + in stock ─────────────────────────────────────────
    out_of_stock = get_out_of_stock_names()

    candidates = [
        (name, details)
        for name, details in SNEAKER_CATALOG.items()
        if details.get("retail_price", 0) <= budget
        and name not in out_of_stock
    ]

    candidates.sort(
        key=lambda x: x[1].get("sales_this_period", 0),
        reverse=True,
    )

    candidates = candidates[:MAX_CATALOG_SIZE]

    catalog_lines = []
    for name, d in candidates:
        catalog_lines.append(
            f"  - {name} | {d['brand']} | ${d['retail_price']} retail"
            f" | ${d.get('market_value', 0)} market | {d.get('profile', '?')}-top"
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

    response = llm.invoke([
        HumanMessage(content=f"""
You are a sneaker expert and stylist. The user has a budget of ${budget:.2f}.

Available sneakers (name | brand | retail | market value | profile):
{catalog_text}
{feedback_block}
User request: {user_input}

Pick 2-3 sneakers that together stay within the total budget, match the
user's preferences, and offer brand variety.

Respond in EXACTLY this format:
REASONING: <2-3 sentences explaining how these picks fit the user's budget,
style preferences, and why you chose this mix of brands. If correcting after
rejection, say what you changed>
ANSWER: <comma-separated list of sneaker names spelled exactly as shown>

Example:
REASONING: Both stay under budget and lean toward the low-top, neutral look the
user asked for, while mixing Jordan and Nike for variety.
ANSWER: Jordan 4 Retro SB Pine Green, Nike Dunk Low Retro White Black
""")
    ])

    reasoning, answer = split_reasoning_answer(response.content)
    raw_answer = answer.lower()

    proposed_sneakers = [
        name for name in SNEAKER_CATALOG
        if name.lower() in raw_answer
    ]

    return {
        "proposed_sneakers": proposed_sneakers,
        "output":  "Sneaker recommendations: " + ", ".join(proposed_sneakers),
        "next":    "critique_agent",
        "reasoning": reasoning,
    }
