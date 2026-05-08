from langgraph.graph import END

from data.catalog import SNEAKER_CATALOG


def logistics_agent(state):
    """
    logistics_agent
    ---------------
    Takes the sneakers proposed by sneaker_agent and checks each one against
    SNEAKER_CATALOG to confirm availability, price, and market value.
    Builds a plain-text availability report with a StockX link for each sneaker.
    This agent always ends the flow.

    Args:
        state (AgentState): reads 'proposed_sneakers'

    Returns:
        dict: updates 'output' and 'next'
    """
    print("\n[logistics_agent] Running...")

    proposed_sneakers = state.get("proposed_sneakers", [])

    if len(proposed_sneakers) == 0:
        print("[logistics_agent] No sneakers to check.")
        return {
            "output": "No sneakers to check availability for.",
            "next": END,
        }

    report_lines = []
    report_lines.append("Sneaker Availability Report:")
    report_lines.append("")

    total_retail = 0.0

    for sneaker_name in proposed_sneakers:
        sneaker = SNEAKER_CATALOG.get(sneaker_name)

        if sneaker is None:
            report_lines.append("  - " + sneaker_name + ": not found in catalog")
            continue

        retail_price = sneaker["retail_price"]
        market_value = sneaker["market_value"]
        link = sneaker["link"]
        brand = sneaker["brand"]
        colorway = sneaker["colorway"]
        total_retail = total_retail + retail_price

        if sneaker["in_stock"] is True:
            status = "IN STOCK"
        else:
            status = "OUT OF STOCK"

        print(f"[logistics_agent] {sneaker_name}: {status} @ ${retail_price:.2f} retail")

        line = (
            "  - "
            + sneaker_name
            + " (" + brand + ")"
            + "  |  " + colorway
            + "  |  " + status
            + "  |  Retail: $" + str(retail_price)
            + "  |  Market: $" + str(market_value)
            + "  |  " + link
        )
        report_lines.append(line)

    report_lines.append("")
    report_lines.append("  Estimated retail total: $" + str(round(total_retail, 2)))

    report = "\n".join(report_lines)

    print(f"[logistics_agent] Done. Estimated retail total: ${total_retail:.2f}")

    return {
        "output": report,
        "next": END,
    }
