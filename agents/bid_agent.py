"""
bid_agent.py
------------
Evaluates whether a user's bid on a specific sneaker is fair, using real
market pricing data (retail price, market value, lowest ask, last sale).

Unlike the shopping-recommendation pipeline (orchestrator → sneaker_agent
→ critique_agent → logistics_agent), bidding targets one already-known
sneaker the user picked themselves, so this runs as a standalone
evaluation rather than a LangGraph node in the multi-agent graph.

If accepted, the caller (api.py) purchases the sneaker immediately —
inventory decrements and it's added to the bidder's wardrobe, the same
mechanics as the existing flat-price Purchase button.
"""

from langchain_core.messages import HumanMessage

from llm import llm
from reasoning import split_reasoning_answer


def validate_bid_request(sneaker_name, bid_amount, catalog, out_of_stock_names):
    """
    validate_bid_request
    ---------------------
    Deterministic pre-checks that don't need an LLM call — a bid on a
    sneaker that doesn't exist, is out of stock, or isn't a positive
    dollar amount is invalid regardless of price, so there's no market
    judgment to make.

    Args:
        sneaker_name       (str):   exact catalog name being bid on
        bid_amount         (float): the offered dollar amount
        catalog            (dict):  {name: details} — SNEAKER_CATALOG or a test double
        out_of_stock_names (set):   names with zero live inventory

    Returns:
        tuple[bool, str|None]: (is_valid, rejection_reason). rejection_reason
                                is None when is_valid is True.
    """
    if sneaker_name not in catalog:
        return False, f"'{sneaker_name}' is not a real catalog item."

    if sneaker_name in out_of_stock_names:
        return False, f"'{sneaker_name}' is out of stock — there's nothing left to bid on."

    if bid_amount is None or bid_amount <= 0:
        return False, "Bid must be a positive dollar amount."

    return True, None


def evaluate_bid(sneaker_name, bid_amount, catalog, out_of_stock_names):
    """
    evaluate_bid
    ------------
    Decides whether a bid is fair, given the sneaker's real market data.

    Runs validate_bid_request first — an invalid bid (unknown sneaker,
    out of stock, non-positive amount) is rejected without an LLM call,
    since those are facts, not judgment calls. Otherwise, an LLM judges
    fairness against retail price, market value, lowest ask, and last
    sale, explaining its reasoning in plain English.

    Args:
        sneaker_name       (str):   exact catalog name being bid on
        bid_amount         (float): the offered dollar amount
        catalog            (dict):  {name: details} — SNEAKER_CATALOG
        out_of_stock_names (set):   names with zero live inventory

    Returns:
        dict: {"accepted": bool, "reasoning": str}
    """
    is_valid, rejection_reason = validate_bid_request(
        sneaker_name, bid_amount, catalog, out_of_stock_names
    )
    if not is_valid:
        return {"accepted": False, "reasoning": rejection_reason}

    details = catalog[sneaker_name]
    retail  = details.get("retail_price", 0)
    market  = details.get("market_value", 0)
    ask     = details.get("lowest_ask", market)
    last    = details.get("last_sale", market)

    response = llm.invoke([
        HumanMessage(content=f"""
You are a sneaker resale pricing expert deciding whether to accept a buyer's bid
on behalf of the seller.

Sneaker: {sneaker_name}
Retail price: ${retail}
Current market value: ${market}
Lowest ask (cheapest currently listed price): ${ask}
Last sale price: ${last}

Buyer's bid: ${bid_amount:.2f}

Decide if this bid is fair given the real market data above. A bid at or
reasonably close to the lowest ask or last sale price is fair. A bid far
below market value and the lowest ask is not fair to the seller.

Respond in EXACTLY this format:
REASONING: <2-3 sentences comparing the bid to the real pricing data above>
ANSWER: ACCEPT   (if the bid is fair)
        or
ANSWER: REJECT   (if the bid is too low)
""")
    ])

    reasoning, answer = split_reasoning_answer(response.content)
    accepted = answer.strip().upper().startswith("ACCEPT")

    return {"accepted": accepted, "reasoning": reasoning}
