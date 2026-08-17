from langgraph.graph import END

from data.catalog import SNEAKER_CATALOG
from database import get_sneaker_quantity


def logistics_agent(state):
    """
    logistics_agent
    ---------------
    Checks the live DB inventory for each proposed sneaker and builds an
    availability report. Uses get_sneaker_quantity() so the status reflects
    actual stock (quantity > 0) rather than the static in_stock field from
    sneakerdata.json.

    Args:
        state (AgentState): reads 'proposed_sneakers'

    Returns:
        dict: updates 'output', 'next', 'reasoning'
    """
    proposed_sneakers = state.get("proposed_sneakers", [])

    if not proposed_sneakers:
        return {
            "output": "No sneakers to check availability for.",
            "next":   END,
            "reasoning": (
                "No approved picks were passed in, so there is nothing to check "
                "stock for. Ending the pipeline."
            ),
        }

    report_lines = ["Sneaker Availability Report:", ""]
    total_retail  = 0.0

    for sneaker_name in proposed_sneakers:
        sneaker = SNEAKER_CATALOG.get(sneaker_name)

        if sneaker is None:
            report_lines.append(f"  - {sneaker_name}: not found in catalog")
            continue

        retail_price  = sneaker["retail_price"]
        market_value  = sneaker["market_value"]
        total_retail += retail_price

        # Live inventory check from the database
        quantity = get_sneaker_quantity(sneaker_name)
        status   = f"IN STOCK ({quantity} available)" if quantity > 0 else "OUT OF STOCK"

        report_lines.append(
            f"  - {sneaker_name} ({sneaker['brand']})"
            f"  |  {status}"
            f"  |  Retail: ${retail_price}"
            f"  |  Market: ${market_value}"
            f"  |  {sneaker['link']}"
        )

    report_lines += ["", f"  Estimated retail total: ${round(total_retail, 2)}"]

    return {
        "output": "\n".join(report_lines),
        "next":   END,
        "reasoning": (
            f"Checked live database stock for {len(proposed_sneakers)} approved "
            f"pick(s) and totalled their retail price (${round(total_retail, 2)}). "
            "This is the final step, so the pipeline ends here."
        ),
    }
