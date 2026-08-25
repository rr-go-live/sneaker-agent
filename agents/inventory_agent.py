from langchain_core.messages import HumanMessage
from langgraph.graph import END

from data.catalog import USER_SNEAKER_COLLECTION
from database import get_user_wardrobe
from llm import llm


def inventory_agent(state):
    """
    inventory_agent
    ---------------
    Reviews the user's sneaker collection and decides whether to also shop.

    Collection resolution priority:
      1. Web path  — sneaker_collection already in state (from UI form).
      2. DB path   — looks up wardrobe rows from SQLite by user_name.
      3. CLI path  — falls back to USER_SNEAKER_COLLECTION dict.

    A second LLM call then decides whether the user also wants to buy new
    sneakers. If yes → sneaker_agent. If no → ends the flow here.

    Args:
        state (AgentState): reads 'sneaker_collection' (opt), 'user_name', 'input'

    Returns:
        dict: updates 'sneaker_collection', 'output', 'next'
    """
    user_input = state.get("input", "")
    user_name  = state.get("user_name", "")

    # Web path: collection passed from the UI form
    sneaker_collection = state.get("sneaker_collection")

    if not sneaker_collection:
        # DB path: fetch from SQLite
        sneaker_collection = get_user_wardrobe(user_name)

    if not sneaker_collection:
        # CLI fallback
        sneaker_collection = USER_SNEAKER_COLLECTION.get(user_name, [])

    collection_text = (
        ", ".join(sneaker_collection) if sneaker_collection
        else "an empty sneaker collection"
    )

    # Step 1 — Summarize the collection
    response = llm.invoke([
        HumanMessage(content=f"""
You are a sneaker expert reviewing someone's sneaker collection.

They currently own: {collection_text}

User request: {user_input}

Briefly summarize what they have and suggest 1-2 outfit pairings or occasions
where these sneakers would work well. Keep the response under 80 words.
""")
    ])

    summary = response.content.strip()

    # Step 2 — Decide whether to continue shopping
    routing_response = llm.invoke([
        HumanMessage(content=f"""
The user said: "{user_input}"

After reviewing their sneaker collection, does the user also want to buy new
sneakers or add to their collection?

Return ONLY one of these two words:
- shop   (if they want to buy new sneakers or add to their collection)
- done   (if they only want to see what they already own)
""")
    ])

    routing_answer = routing_response.content.strip().lower()
    wants_to_shop = "shop" in routing_answer
    next_agent = "sneaker_agent" if wants_to_shop else END

    if wants_to_shop:
        reasoning = (
            f"Reviewed {len(sneaker_collection)} item(s) in the collection and "
            "detected buying intent in the request, so I'm handing off to the "
            "sneaker agent to find new picks."
        )
    else:
        reasoning = (
            f"Reviewed {len(sneaker_collection)} item(s) in the collection. The "
            "request only asks about what is already owned, so no shopping step "
            "is needed and the pipeline can stop here."
        )

    return {
        "sneaker_collection": sneaker_collection,
        "output": summary,
        "next":   next_agent,
        "reasoning": reasoning,
    }
