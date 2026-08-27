from langchain_core.messages import HumanMessage

from data.catalog import SNEAKER_CATALOG
from database import get_out_of_stock_names
from llm import llm
from reasoning import split_reasoning_answer
from agents.selection import (
    filter_by_brand, filter_by_color, filter_by_profile, filter_by_max_price,
    filter_by_release_year, sort_candidates,
    extract_requested_count, extract_proposed_names, extract_requested_brands,
    extract_requested_colors, extract_profile, extract_max_price,
    extract_min_release_year, extract_sort_preference,
    clamp_count_to_pool, DEFAULT_PICK_COUNT,
)

# Max catalog rows sent to the LLM — keeps prompt size manageable
# while still giving good variety (1 668 total sneakers in catalog).
MAX_CATALOG_SIZE = 80


def sneaker_agent(state):
    """
    sneaker_agent
    -------------
    Picks sneakers from the catalog matching every constraint the user
    stated — brand, colorway, silhouette, retail ceiling, release year,
    ordering, and pick count.

    Constraints arrive two ways: as structured fields from the Advisor UI's
    filter chips, or named in prose ("a low top jordan under $150") from the
    free-text box, the admin Custom Scenario panel, or the CLI. Structured
    fields win when present; otherwise the same constraints are parsed from
    the text by the extract_* helpers in selection.py. Without that fallback
    a brand the user plainly named was dropped, and the prompt then told the
    LLM to favor brand variety — steering it away from what was asked for.

    Compliance is enforced deterministically rather than left to prompt
    wording, since an LLM can silently ignore or contradict a soft
    instruction:
      1. Drop anything out of stock
      2. Hard-filter to the requested brand(s), silhouette, retail ceiling,
         and release-year floor. All four are exact, always-present catalog
         fields, so a request with zero matches correctly yields no picks
         and says which combination failed — never a silent substitution
      3. Prefer the requested color(s), if any (colorway data is missing
         catalog-wide, so this matches on name and falls back to the full
         pool rather than an empty result — the LLM is told plainly whether
         a real color match was found)
      4. Order the pool — by retail price when the user asked for a
         superlative, otherwise by sales_this_period (popularity) — and cap
         at MAX_CATALOG_SIZE. Ordering must happen before the cap, or a
         superlative query's correct answer never reaches the LLM at all
      5. After the LLM answers, keep only names that were actually in the
         candidate pool shown to it — guards against a hallucinated pick
         bypassing every filter above

    The requested pick count is parsed from the free-text input (e.g. "just
    2 options"); DEFAULT_PICK_COUNT is used when none is stated.

    If critique_feedback is present in state (retry after rejection), the
    feedback is included in the prompt so the LLM can correct its picks.

    Args:
        state (AgentState): reads 'input', 'critique_feedback',
                            'requested_brands', 'requested_colors',
                            'requested_profile'

    Returns:
        dict: updates 'proposed_sneakers', 'requested_brands',
              'requested_colors', 'output', 'next', 'requested_count',
              'reasoning'
    """
    user_input        = state.get("input", "")
    critique_feedback = state.get("critique_feedback")
    requested_count   = extract_requested_count(user_input, default=DEFAULT_PICK_COUNT)

    # ── Resolve constraints: structured fields first, free text as fallback ──
    # An explicit UI chip selection is a stronger signal than a phrase in a
    # sentence, so structured fields win when both are present. When they're
    # absent (admin Custom Scenario, CLI, or the Advisor's free-text box),
    # the same constraints are parsed out of the prose instead — otherwise a
    # brand the user plainly named would be dropped entirely.
    requested_brands = state.get("requested_brands") or []
    if not requested_brands:
        catalog_brands = {details.get("brand", "") for details in SNEAKER_CATALOG.values()}
        requested_brands = extract_requested_brands(user_input, catalog_brands)

    requested_colors = state.get("requested_colors") or []
    if not requested_colors:
        requested_colors = extract_requested_colors(user_input)

    requested_profile = state.get("requested_profile") or extract_profile(user_input)
    max_price         = extract_max_price(user_input)
    min_release_year  = extract_min_release_year(user_input)
    sort_preference   = extract_sort_preference(user_input)

    # ── Filter: in stock ──────────────────────────────────────────────────────
    out_of_stock = get_out_of_stock_names()

    candidates = [
        (name, details)
        for name, details in SNEAKER_CATALOG.items()
        if name not in out_of_stock
    ]

    # ── Hard-filter the exact-data constraints, soft-prefer color ────────────
    # Brand, profile, retail price and release year are all present and exact
    # in the catalog, so each is a strict filter: a request with zero matches
    # must yield nothing rather than silently returning something that
    # violates what the user asked for. Color is the exception — see
    # filter_by_color for why it falls back instead.
    candidates = filter_by_brand(candidates, requested_brands)
    candidates = filter_by_profile(candidates, requested_profile)
    candidates = filter_by_max_price(candidates, max_price)
    candidates = filter_by_release_year(candidates, min_release_year)
    candidates, color_matched = filter_by_color(candidates, requested_colors)

    # Order before capping — for a superlative query ("highest retail") the
    # correct answer is defined by price, and the default popularity ranking
    # would push it outside the MAX_CATALOG_SIZE window entirely.
    candidates = sort_candidates(candidates, sort_preference)
    candidates = candidates[:MAX_CATALOG_SIZE]

    if not candidates:
        unmet = _describe_constraints(
            requested_brands, requested_profile, max_price, min_release_year
        )
        return {
            "proposed_sneakers": [],
            "requested_brands":  requested_brands,
            "requested_colors":  requested_colors,
            # Flags an unsatisfiable request so critique_agent skips its retry
            # loop. Retrying cannot conjure a match the catalog doesn't hold —
            # it would just burn two more LLM calls and end with a generic
            # "picks approved" message replacing this specific explanation.
            "no_matches": True,
            "output": f"No in-stock sneakers matched {unmet}.",
            "next":   "critique_agent",
            "requested_count": requested_count,
            "reasoning": (
                f"No in-stock catalog entries matched {unmet}, so there is "
                "nothing to propose. Reporting that honestly rather than "
                "widening the search to something the user didn't ask for."
            ),
        }

    original_count  = requested_count
    requested_count = clamp_count_to_pool(requested_count, len(candidates))
    count_clamp_note = ""
    if requested_count < original_count:
        count_clamp_note = (
            f"\nNote: only {len(candidates)} sneaker(s) matched the requested "
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

    # Every filter already applied deterministically is stated as a fact, not
    # a request — the pool cannot violate it, so the LLM only needs to know
    # the constraint is already satisfied and shouldn't second-guess it.
    applied_notes = []
    if requested_profile:
        applied_notes.append(f"all options are {requested_profile}-top silhouettes")
    if max_price is not None:
        applied_notes.append(f"all options retail at ${max_price:.0f} or less")
    if min_release_year is not None:
        applied_notes.append(f"all options released in {min_release_year} or later")
    if sort_preference == "retail_desc":
        applied_notes.append("options are ordered by retail price, highest first")
    elif sort_preference == "retail_asc":
        applied_notes.append("options are ordered by retail price, lowest first")

    applied_note = ""
    if applied_notes:
        applied_note = "\nAlready filtered for you: " + "; ".join(applied_notes) + "."

    response = llm.invoke([
        HumanMessage(content=f"""
You are a sneaker expert and stylist. Pick based on style fit and how well each
option answers the user's request. Retail/market price is shown for reference,
and any price limit the user stated has already been applied to this list.

Available sneakers (name | brand | colorway | retail | market value | profile):
{catalog_text}
{feedback_block}
User request: {user_input}

{brand_instruction}{applied_note}{color_note}{count_clamp_note}

Pick EXACTLY {requested_count} sneaker{'s' if requested_count != 1 else ''} from the list above
that match the user's style. Do not pick more or fewer than {requested_count}.
If the user asked for a superlative (the most expensive, the cheapest), the list
is already ordered so the best answer is at the top — pick from the top.

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
        # Resolved constraints are written back so critique_agent enforces the
        # same brand rule sneaker_agent filtered on — including brands parsed
        # from free text, which never appear in the structured state fields.
        "requested_brands":  requested_brands,
        "requested_colors":  requested_colors,
        "output":  "Sneaker recommendations: " + ", ".join(proposed_sneakers),
        "next":    "critique_agent",
        "requested_count": requested_count,
        "reasoning": reasoning,
    }


def _describe_constraints(brands, profile, max_price, min_release_year):
    """
    _describe_constraints
    ----------------------
    Builds a plain-English description of the filters that produced an empty
    candidate pool, so the user is told which combination had no matches
    instead of a generic "no sneakers found".

    Args:
        brands           (list[str]): resolved brand filter (may be empty)
        profile          (str|None):  resolved silhouette filter
        max_price        (float|None): resolved retail ceiling
        min_release_year (int|None):   resolved release-year floor

    Returns:
        str: e.g. "brand(s) Jordan, low-top, under $150" — or "the requested
              filters" when nothing specific was set
    """
    parts = []

    if brands:
        parts.append(f"brand(s) {', '.join(brands)}")
    if profile:
        parts.append(f"{profile}-top")
    if max_price is not None:
        parts.append(f"under ${max_price:.0f}")
    if min_release_year is not None:
        parts.append(f"released {min_release_year} or later")

    if not parts:
        return "the requested filters"

    return ", ".join(parts)
