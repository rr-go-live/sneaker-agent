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

    Emits the report twice, in two shapes, because two very different
    consumers need it:
      - 'availability' — structured rows the web UI renders as a real table.
      - 'output'       — a plain-text version for the CLI and eval report,
                         where there is no table to render.

    Neither includes the raw StockX URL. It is long enough to dominate a
    line of text, and the UI turns 'link' into a short labelled link instead.

    Args:
        state (AgentState): reads 'proposed_sneakers'

    Returns:
        dict: updates 'availability', 'retail_total', 'output', 'next',
              'reasoning'
    """
    proposed_sneakers = state.get("proposed_sneakers", [])

    if not proposed_sneakers:
        # An upstream agent may already have explained WHY there are no picks
        # (e.g. "No in-stock sneakers matched brand(s) Jordan, under $10").
        # That reason is far more useful than a generic line, so it is passed
        # through rather than overwritten — the user asked for something the
        # catalog can't satisfy and deserves to be told which part failed.
        upstream_output = (state.get("output") or "").strip()

        return {
            "output": upstream_output or "No sneakers to check availability for.",
            "next":   END,
            "reasoning": (
                "No approved picks were passed in, so there is nothing to check "
                "stock for. Keeping the upstream explanation of why the search "
                "came back empty, and ending the pipeline."
            ),
        }

    availability = []
    total_retail = 0.0

    for sneaker_name in proposed_sneakers:
        sneaker = SNEAKER_CATALOG.get(sneaker_name)

        if sneaker is None:
            availability.append({
                "name":     sneaker_name,
                "brand":    "",
                "in_stock": False,
                "quantity": 0,
                "retail":   None,
                "market":   None,
                "link":     None,
                "found":    False,
            })
            continue

        retail_price  = sneaker["retail_price"]
        market_value  = sneaker["market_value"]
        total_retail += retail_price

        # Live inventory check from the database
        quantity = get_sneaker_quantity(sneaker_name)

        availability.append({
            "name":     sneaker_name,
            "brand":    sneaker["brand"],
            "in_stock": quantity > 0,
            "quantity": quantity,
            "retail":   retail_price,
            "market":   market_value,
            "link":     sneaker["link"],
            "found":    True,
        })

    total_retail = round(total_retail, 2)

    return {
        "availability": availability,
        "retail_total": total_retail,
        "output":       _format_report_text(availability, total_retail),
        "next":         END,
        "reasoning": (
            f"Checked live database stock for {len(proposed_sneakers)} approved "
            f"pick(s) and totalled their retail price (${total_retail}). "
            "This is the final step, so the pipeline ends here."
        ),
    }


def _format_report_text(availability, total_retail):
    """
    _format_report_text
    --------------------
    Renders the availability rows as aligned plain text for the CLI and the
    eval report, which have no table to render into.

    Column widths are measured from the actual rows rather than fixed, so
    long sneaker names don't push the later columns out of alignment.

    Args:
        availability (list[dict]): rows built by logistics_agent
        total_retail (float):      summed retail price of every found row

    Returns:
        str: the formatted multi-line report
    """
    if not availability:
        return "No sneakers to check availability for."

    name_column   = max(len(row["name"]) for row in availability)
    brand_column  = max(len(row["brand"]) for row in availability)
    status_column = len("OUT OF STOCK")

    lines = ["Sneaker Availability Report:", ""]

    for row in availability:
        if not row["found"]:
            lines.append(f"  {row['name'].ljust(name_column)}   not found in catalog")
            continue

        status = f"IN STOCK ({row['quantity']})" if row["in_stock"] else "OUT OF STOCK"

        lines.append(
            f"  {row['name'].ljust(name_column)}"
            f"   {row['brand'].ljust(brand_column)}"
            f"   {status.ljust(status_column)}"
            f"   retail ${row['retail']:>7,.2f}"
            f"   market ${row['market']:>7,.2f}"
        )

    lines += ["", f"  Estimated retail total: ${total_retail:,.2f}"]

    return "\n".join(lines)
