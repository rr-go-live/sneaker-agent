from langchain_core.messages import HumanMessage
from langgraph.graph import END

from data.catalog import USER_SNEAKER_COLLECTION
from llm import llm


def inventory_agent(state):
    """
    inventory_agent
    ---------------
    Looks up what sneakers the user already owns, then asks the LLM to summarize
    the collection and suggest pairing ideas.

    A second LLM call then decides whether the user also wants to shop for new
    sneakers. If yes, the flow continues to financial_agent. If no, it stops here.

    This LLM-based routing is what makes the 4-agent chain possible — the agent
    uses the model to determine its own next step rather than hard-coded logic.

    Args:
        state (AgentState): reads 'user_name' and 'input'

    Returns:
        dict: updates 'sneaker_collection', 'output', and 'next'
    """
    print("\n[inventory_agent] Running...")

    user_name = state.get("user_name", "John")
    user_input = state.get("input", "")

    sneaker_collection = USER_SNEAKER_COLLECTION.get(user_name, [])
    print(f"[inventory_agent] {user_name}'s sneaker collection: {sneaker_collection}")

    if len(sneaker_collection) == 0:
        collection_text = "an empty sneaker collection"
    else:
        collection_text = ", ".join(sneaker_collection)

    # Step 1 — Ask the LLM to summarize the collection and suggest pairings
    response = llm.invoke([
        HumanMessage(content=f"""
You are a sneaker expert reviewing someone's sneaker collection.

{user_name} currently owns: {collection_text}

User request: {user_input}

Briefly summarize what they have and suggest 1-2 outfit pairings or occasions
where these sneakers would work well. Keep the response under 80 words.
""")
    ])

    summary = response.content.strip()
    print("[inventory_agent] Collection summary received from LLM.")

    # Step 2 — Ask a separate LLM question to decide where to route next
    print("[inventory_agent] Asking LLM whether the user also wants to shop...")

    routing_response = llm.invoke([
        HumanMessage(content=f"""
The user said: "{user_input}"

After reviewing their sneaker collection, does the user also want to buy new sneakers
or add to their collection?

Return ONLY one of these two words:
- shop   (if they want to buy new sneakers or add to their collection)
- done   (if they only want to see what they already own)
""")
    ])

    routing_answer = routing_response.content.strip().lower()
    print("[inventory_agent] LLM routing answer: '" + routing_answer + "'")

    if "shop" in routing_answer:
        print("[inventory_agent] User wants to shop — handing off to financial_agent...")
        next_agent = "financial_agent"
    else:
        print("[inventory_agent] User only wanted collection info — stopping here.")
        next_agent = END

    return {
        "sneaker_collection": sneaker_collection,
        "output": summary,
        "next": next_agent,
    }
