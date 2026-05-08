from langchain_core.messages import HumanMessage

from data.catalog import SNEAKER_CATALOG
from llm import llm


def sneaker_agent(state):
    """
    sneaker_agent
    -------------
    Asks the LLM to pick 2-3 sneakers from the catalog that fit the user's budget.
    The full catalog is passed to the LLM so it can choose based on budget and the
    user's stated preferences. The LLM's picks are then validated against the real
    catalog to prevent it from recommending sneakers that do not exist.

    Args:
        state (AgentState): reads 'budget' and 'input'

    Returns:
        dict: updates 'proposed_sneakers', 'output', and 'next'
    """
    print("\n[sneaker_agent] Running...")

    budget = state.get("budget", 0)
    user_input = state.get("input", "")

    # Build a plain-text list of the catalog for the LLM to read
    catalog_lines = []
    for sneaker_name, details in SNEAKER_CATALOG.items():
        line = (
            "  - "
            + sneaker_name
            + " | "
            + details["brand"]
            + " | "
            + details["colorway"]
            + " | $"
            + str(details["retail_price"])
        )
        catalog_lines.append(line)

    catalog_text = "\n".join(catalog_lines)

    print(f"[sneaker_agent] Budget available: ${budget:.2f}")
    print("[sneaker_agent] Catalog being sent to LLM:")
    print(catalog_text)

    response = llm.invoke([
        HumanMessage(content=f"""
You are a sneaker expert and stylist. The user has a budget of ${budget:.2f}.

Sneakers available in the catalog (name | brand | colorway | retail price):
{catalog_text}

User request: {user_input}

Select 2-3 sneakers from the list above that together stay within the total budget
and match the user's style or stated preferences. Consider brand variety.

Return ONLY a comma-separated list of sneaker names spelled exactly as shown above.
No explanation, no extra text.

Example: Nike SB Dunk High Oski Great White, Adidas Busenitz Vintage Focus Orange
""")
    ])

    raw_response = response.content.strip().lower()
    print(f"[sneaker_agent] LLM said: '{raw_response}'")

    # Validate picks against the real catalog so the LLM cannot invent names
    proposed_sneakers = []
    for sneaker_name in SNEAKER_CATALOG:
        if sneaker_name.lower() in raw_response:
            proposed_sneakers.append(sneaker_name)

    print(f"[sneaker_agent] Matched sneakers from catalog: {proposed_sneakers}")
    print("[sneaker_agent] Passing picks to logistics_agent to check availability...")

    sneakers_as_text = ", ".join(proposed_sneakers)

    return {
        "proposed_sneakers": proposed_sneakers,
        "output": "Sneaker recommendations: " + sneakers_as_text,
        "next": "logistics_agent",
    }
