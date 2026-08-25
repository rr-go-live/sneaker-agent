"""
cli_test.py
-----------
Command-line test harness for the Sneaker Agent application.

Runs every major flow end to end without any manual input, so it can be
used during development or in CI to confirm the app still works after a
change. Run it with:

    python cli_test.py

Design notes:
  - Structural tests (reasoning parser, catalog filtering, user routes,
    database helpers) run fully offline and never call the LLM.
  - The full multi-agent pipeline test makes real Gemini calls, so it only
    runs when a real GOOGLE_API_KEY is available. Otherwise it is reported
    as SKIPPED rather than failed, and the harness still exits successfully.
  - A dummy key is injected when none is present so that importing the API
    (which constructs the LLM client at import time) does not crash the
    offline tests.

The exit code is 0 when every test passes or is skipped, and 1 when any
test fails — which makes it safe to wire into a CI pipeline.
"""

import os
import sys

from dotenv import load_dotenv


# Load .env first so a real GOOGLE_API_KEY (if configured) is available.
load_dotenv()

# Remember whether a real key exists BEFORE we inject a dummy fallback.
HAS_REAL_KEY = bool(os.environ.get("GOOGLE_API_KEY"))

# The API and graph modules build the LLM client at import time, which
# requires *some* key to be present. Inject a harmless dummy when none is
# configured so the offline structural tests can still import and run.
if not HAS_REAL_KEY:
    os.environ["GOOGLE_API_KEY"] = "cli-test-dummy-key"


# Simple pass/fail/skip accounting shared by every test.
RESULTS = []


def record(name, status, detail=""):
    """
    record
    ------
    Stores and prints the outcome of a single test.

    Args:
        name   (str): human-readable test name.
        status (str): one of "PASS", "FAIL", "SKIP".
        detail (str): optional extra context shown after the status.

    Returns:
        None. Appends to the module-level RESULTS list as a side effect.
    """
    RESULTS.append((name, status, detail))

    symbols = {"PASS": "PASS ", "FAIL": "FAIL ", "SKIP": "SKIP "}
    prefix = symbols.get(status, status)
    line = f"  [{prefix}] {name}"
    if detail:
        line = line + f" — {detail}"
    print(line)


def check(condition, name, detail=""):
    """
    check
    -----
    Records a PASS when the condition is truthy, otherwise a FAIL.

    Args:
        condition (bool): the assertion result to evaluate.
        name      (str):  test name to record.
        detail    (str):  optional context (shown especially on failure).

    Returns:
        bool: the boolean value of the condition, so callers can branch.
    """
    if condition:
        record(name, "PASS")
        return True

    record(name, "FAIL", detail or "condition was false")
    return False


def test_reasoning_parser():
    """
    test_reasoning_parser
    ---------------------
    Verifies the REASONING/ANSWER splitter used by the LLM agents handles
    the well-formed case, the answer-only case, the label-free fallback,
    lowercase labels, and empty input.

    Returns:
        None. Records one result per assertion.
    """
    print("\nReasoning parser")
    from reasoning import split_reasoning_answer

    reasoning, answer = split_reasoning_answer("REASONING: because.\nANSWER: financial_agent")
    check(
        reasoning == "because." and answer == "financial_agent",
        "parses a well-formed REASONING/ANSWER response",
        f"got reasoning={reasoning!r} answer={answer!r}",
    )

    reasoning, answer = split_reasoning_answer("ANSWER: sneaker_agent")
    check(
        reasoning == "" and answer == "sneaker_agent",
        "handles an answer-only response",
        f"got reasoning={reasoning!r} answer={answer!r}",
    )

    reasoning, answer = split_reasoning_answer("financial_agent")
    check(
        answer == "financial_agent",
        "falls back to whole-string answer when unlabeled",
        f"got answer={answer!r}",
    )

    reasoning, answer = split_reasoning_answer("reasoning: lower\nanswer: done")
    check(
        reasoning == "lower" and answer == "done",
        "is case-insensitive about the labels",
        f"got reasoning={reasoning!r} answer={answer!r}",
    )

    reasoning, answer = split_reasoning_answer("")
    check(
        reasoning == "" and answer == "",
        "handles empty input without raising",
        f"got reasoning={reasoning!r} answer={answer!r}",
    )


def test_catalog_filter():
    """
    test_catalog_filter
    -------------------
    Exercises GET /api/sneakers, including a search query that previously
    crashed because some catalog entries have no 'colorway' key. Confirms
    the endpoint now returns HTTP 200 and well-formed rows.

    Returns:
        None. Records one result per assertion.
    """
    print("\nCatalog filter endpoint")
    from fastapi.testclient import TestClient
    from api import app

    client = TestClient(app)

    # A plain search that touches entries with and without a colorway field.
    response = client.get("/api/sneakers", params={"q": "panda"})
    check(
        response.status_code == 200,
        "GET /api/sneakers?q=panda returns 200 (missing-colorway safe)",
        f"status={response.status_code}",
    )

    rows = response.json() if response.status_code == 200 else []
    check(
        isinstance(rows, list),
        "search response is a JSON list",
        f"type={type(rows).__name__}",
    )

    if rows:
        first = rows[0]
        check(
            "name" in first,
            "each result row includes a 'name' field",
            f"keys={list(first.keys())}",
        )

    # A price filter should never return anything above the ceiling.
    response = client.get("/api/sneakers", params={"max_price": 120})
    within_budget = all(item.get("retail_price", 0) <= 120 for item in response.json())
    check(
        response.status_code == 200 and within_budget,
        "max_price filter excludes over-budget sneakers",
        f"status={response.status_code}",
    )


def test_user_routes():
    """
    test_user_routes
    ----------------
    Confirms the user profile routes behave: the list route returns a list,
    an unknown username returns 404, and a known user (if any are seeded)
    returns a wardrobe list.

    Returns:
        None. Records one result per assertion.
    """
    print("\nUser profile routes")
    from fastapi.testclient import TestClient
    from api import app

    client = TestClient(app)

    response = client.get("/api/users")
    users = response.json() if response.status_code == 200 else []
    check(
        response.status_code == 200 and isinstance(users, list),
        "GET /api/users returns a list",
        f"status={response.status_code}",
    )

    response = client.get("/api/users/definitely-not-a-real-user-xyz")
    check(
        response.status_code == 404,
        "unknown username returns 404",
        f"status={response.status_code}",
    )

    if users:
        username = users[0]["username"]
        response = client.get(f"/api/users/{username}")
        body = response.json() if response.status_code == 200 else {}
        check(
            response.status_code == 200 and isinstance(body.get("wardrobe"), list),
            f"known user '{username}' returns a wardrobe list",
            f"status={response.status_code}",
        )
    else:
        record("known-user lookup", "SKIP", "no seeded users to test")


def test_database_helpers():
    """
    test_database_helpers
    ---------------------
    Confirms the core database helpers initialise cleanly and return the
    expected types, without depending on any particular seeded data.

    Returns:
        None. Records one result per assertion.
    """
    print("\nDatabase helpers")
    from database import init_db, get_sneaker_quantity, get_out_of_stock_names

    init_db()
    record("init_db runs without error", "PASS")

    quantity = get_sneaker_quantity("Jordan 4 Retro SB Pine Green")
    check(
        isinstance(quantity, int) and quantity >= 0,
        "get_sneaker_quantity returns a non-negative int",
        f"value={quantity!r}",
    )

    out_of_stock = get_out_of_stock_names()
    check(
        isinstance(out_of_stock, set),
        "get_out_of_stock_names returns a set",
        f"type={type(out_of_stock).__name__}",
    )


def test_selection_logic():
    """
    test_selection_logic
    ---------------------
    Pure-function tests for agents/selection.py — the deterministic filtering
    and validation logic sneaker_agent uses to guarantee brand/color/count
    compliance, instead of relying on the LLM to follow soft prompt wording.

    No LLM or database calls — these must be fast and fully deterministic.

    Returns:
        None. Records one result per assertion.
    """
    print("\nSelection logic (deterministic filtering)")
    from agents.selection import (
        filter_by_brand, filter_by_color, extract_requested_count,
        extract_proposed_names, clamp_count_to_pool,
    )

    candidates = [
        ("Jordan 4 Retro SB Pine Green",  {"brand": "Jordan", "colorway": "Pine Green"}),
        ("Jordan 1 Retro High OG Bred",   {"brand": "Jordan", "colorway": "Black/Red"}),
        ("Nike Dunk Low Grey Fog",        {"brand": "Nike",   "colorway": "Grey Fog"}),
        ("adidas Adilette 22 Slides",     {"brand": "adidas", "colorway": "Sand"}),
    ]

    # ── filter_by_brand ──────────────────────────────────────────────────
    result = filter_by_brand(candidates, [])
    check(result == candidates, "filter_by_brand: no brands requested returns all candidates unchanged")

    result = filter_by_brand(candidates, ["Jordan"])
    check(
        [n for n, _ in result] == ["Jordan 4 Retro SB Pine Green", "Jordan 1 Retro High OG Bred"],
        "filter_by_brand: filters to only the requested brand",
        f"got {[n for n, _ in result]}",
    )

    result = filter_by_brand(candidates, ["jordan"])
    check(
        len(result) == 2,
        "filter_by_brand: brand match is case-insensitive",
        f"got {len(result)} results",
    )

    result = filter_by_brand(candidates, ["New Balance"])
    check(
        result == [],
        "filter_by_brand: a brand with zero matches returns an empty list (not silently ignored)",
        f"got {[n for n, _ in result]}",
    )

    # ── filter_by_color ──────────────────────────────────────────────────
    result, matched = filter_by_color(candidates, [])
    check(
        result == candidates and matched is True,
        "filter_by_color: no colors requested returns all candidates unchanged",
    )

    result, matched = filter_by_color(candidates, ["Grey"])
    check(
        [n for n, _ in result] == ["Nike Dunk Low Grey Fog"] and matched is True,
        "filter_by_color: matches candidates whose colorway contains the requested color",
        f"got {[n for n, _ in result]}, matched={matched}",
    )

    result, matched = filter_by_color(candidates, ["Purple"])
    check(
        result == candidates and matched is False,
        "filter_by_color: no candidate matches falls back to the full pool and reports matched=False",
        f"got {len(result)} results, matched={matched}",
    )

    # ── extract_requested_count ──────────────────────────────────────────
    check(
        extract_requested_count("I'm looking for new sneakers", default=5) == 5,
        "extract_requested_count: no number mentioned falls back to the default",
    )

    check(
        extract_requested_count("high top released after 2020", default=5) == 5,
        "extract_requested_count: an unrelated number (a year) is not mistaken for a count",
    )

    check(
        extract_requested_count("give me just 2 options", default=5) == 2,
        "extract_requested_count: parses an explicit digit count",
    )

    check(
        extract_requested_count("show me three pairs", default=5) == 3,
        "extract_requested_count: parses an explicit number-word count",
    )

    check(
        extract_requested_count("I want 20 sneakers", default=5) == 10,
        "extract_requested_count: clamps an unreasonably large request to the max (10)",
    )

    # ── extract_proposed_names ───────────────────────────────────────────
    # Only two of the four candidates were actually shown to the LLM this time.
    shown = candidates[:2]
    raw_answer = "jordan 4 retro sb pine green, adidas adilette 22 slides"
    result = extract_proposed_names(raw_answer, shown)
    check(
        result == ["Jordan 4 Retro SB Pine Green"],
        "extract_proposed_names: ignores a name the LLM mentioned that wasn't in its candidate pool "
        "(guards against hallucinated picks bypassing brand/stock filtering)",
        f"got {result}",
    )

    # ── clamp_count_to_pool ───────────────────────────────────────────────
    check(
        clamp_count_to_pool(5, pool_size=2) == 2,
        "clamp_count_to_pool: reduces an impossible request (5 from a pool of 2) down to the pool size",
    )
    check(
        clamp_count_to_pool(3, pool_size=10) == 3,
        "clamp_count_to_pool: leaves the request unchanged when the pool has enough candidates",
    )
    check(
        clamp_count_to_pool(5, pool_size=0) == 0,
        "clamp_count_to_pool: an empty pool clamps to zero rather than raising",
    )


def test_bid_validation():
    """
    test_bid_validation
    --------------------
    Pure-function tests for agents/bid_agent.validate_bid_request — the
    deterministic pre-checks that reject an invalid bid (unknown sneaker,
    out of stock, non-positive amount) without ever calling the LLM, since
    those aren't market judgment calls.

    No LLM calls — fast and fully deterministic.

    Returns:
        None. Records one result per assertion.
    """
    print("\nBid validation (deterministic pre-checks)")
    from agents.bid_agent import validate_bid_request

    catalog = {
        "Jordan 4 Retro SB Pine Green": {"retail_price": 225, "market_value": 388},
    }
    out_of_stock = {"Nike Dunk Low Grey Fog"}

    is_valid, reason = validate_bid_request(
        "Not A Real Sneaker", 200, catalog, out_of_stock
    )
    check(
        is_valid is False and reason is not None,
        "validate_bid_request: rejects a sneaker that isn't in the catalog",
        f"got is_valid={is_valid}, reason={reason!r}",
    )

    is_valid, reason = validate_bid_request(
        "Nike Dunk Low Grey Fog", 100, {**catalog, "Nike Dunk Low Grey Fog": {"retail_price": 110}}, out_of_stock
    )
    check(
        is_valid is False and reason is not None,
        "validate_bid_request: rejects a bid on an out-of-stock sneaker",
        f"got is_valid={is_valid}, reason={reason!r}",
    )

    is_valid, reason = validate_bid_request(
        "Jordan 4 Retro SB Pine Green", 0, catalog, out_of_stock
    )
    check(
        is_valid is False and reason is not None,
        "validate_bid_request: rejects a zero or negative bid amount",
        f"got is_valid={is_valid}, reason={reason!r}",
    )

    is_valid, reason = validate_bid_request(
        "Jordan 4 Retro SB Pine Green", 200, catalog, out_of_stock
    )
    check(
        is_valid is True and reason is None,
        "validate_bid_request: a real, in-stock sneaker with a positive bid passes validation",
        f"got is_valid={is_valid}, reason={reason!r}",
    )


def test_full_pipeline():
    """
    test_full_pipeline
    ------------------
    Runs the complete multi-agent graph for a buying request and confirms
    that every node emits reasoning and the sneaker agent proposes picks.
    There is no budget in this app, so there's nothing to check picks
    against on that front — any in-stock sneaker is a valid candidate.

    Skipped when no real GOOGLE_API_KEY is configured, since it makes live
    Gemini calls.

    Returns:
        None. Records one result per assertion, or a single SKIP.
    """
    print("\nFull multi-agent pipeline")

    if not HAS_REAL_KEY:
        record("full pipeline", "SKIP", "no GOOGLE_API_KEY configured")
        return

    from graph import build_graph

    graph = build_graph()
    initial_state = {
        "input": "I want a clean white low-top for everyday wear that holds resale value",
        "user_name": "cli_test_user",
    }

    nodes_seen = []
    nodes_with_reasoning = []
    final_state = {}

    for chunk in graph.stream(initial_state, stream_mode="updates"):
        for node_name, updates in chunk.items():
            nodes_seen.append(node_name)
            if updates.get("reasoning"):
                nodes_with_reasoning.append(node_name)
            final_state.update(updates)

    check(
        "orchestrator" in nodes_seen and "sneaker_agent" in nodes_seen,
        "pipeline runs through the orchestrator and sneaker agent",
        f"nodes={nodes_seen}",
    )

    check(
        len(nodes_with_reasoning) == len(nodes_seen),
        "every node emits reasoning for the log panel",
        f"{len(nodes_with_reasoning)}/{len(nodes_seen)} nodes had reasoning",
    )

    proposed = final_state.get("proposed_sneakers", [])
    check(
        len(proposed) > 0,
        "sneaker agent proposes at least one pick",
        f"proposed={proposed}",
    )


def test_bid_fairness_judgment():
    """
    test_bid_fairness_judgment
    -----------------------------
    Live regression test proving the LLM fairness judgment actually
    discriminates on real pricing data: a bid far below market value
    should be rejected, and a bid close to the lowest ask should be
    accepted.

    Skipped when no real GOOGLE_API_KEY is configured, since it makes live
    Gemini calls.

    Returns:
        None. Records one result per assertion, or a single SKIP.
    """
    print("\nBid fairness judgment (live LLM)")

    if not HAS_REAL_KEY:
        record("bid fairness judgment", "SKIP", "no GOOGLE_API_KEY configured")
        return

    from data.catalog import SNEAKER_CATALOG
    from database import get_out_of_stock_names
    from agents.bid_agent import evaluate_bid

    sneaker = "Jordan 4 Retro SB Pine Green"
    out_of_stock = get_out_of_stock_names()
    # Real data for this sneaker: retail $225, market $388, lowest ask $325.

    lowball = evaluate_bid(sneaker, 50.0, SNEAKER_CATALOG, out_of_stock)
    check(
        lowball["accepted"] is False,
        "a bid far below retail/market/lowest-ask is rejected",
        f"got {lowball}",
    )

    fair = evaluate_bid(sneaker, 320.0, SNEAKER_CATALOG, out_of_stock)
    check(
        fair["accepted"] is True,
        "a bid close to the lowest ask is accepted",
        f"got {fair}",
    )


def test_brand_and_count_compliance():
    """
    test_brand_and_count_compliance
    ---------------------------------
    Live regression test for the exact reported bug: a Jordan brand filter
    plus a Grey colorway filter, with no explicit count, was returning an
    off-brand (Adidas) pick in the wrong color and only 2 results instead
    of the intended default.

    Confirms end-to-end that: every proposed pick matches the requested
    brand, and the count matches what the deterministic selection logic
    (already unit-tested above) says should be produced for this exact
    candidate pool.

    Skipped when no real GOOGLE_API_KEY is configured, since it makes live
    Gemini calls.

    Returns:
        None. Records one result per assertion, or a single SKIP.
    """
    print("\nBrand/count compliance (regression for reported bug)")

    if not HAS_REAL_KEY:
        record("brand/count compliance", "SKIP", "no GOOGLE_API_KEY configured")
        return

    from data.catalog import SNEAKER_CATALOG
    from database import get_out_of_stock_names
    from graph import build_graph
    from agents.selection import filter_by_brand, filter_by_color, clamp_count_to_pool, DEFAULT_PICK_COUNT

    brands  = ["Jordan"]
    colors  = ["Grey"]

    # Independently compute what a correct run should produce, using the same
    # tested pure functions the agent uses — not a hardcoded guess.
    out_of_stock = get_out_of_stock_names()
    candidates = [
        (name, details) for name, details in SNEAKER_CATALOG.items()
        if name not in out_of_stock
    ]
    candidates = filter_by_brand(candidates, brands)
    candidates, _ = filter_by_color(candidates, colors)
    expected_count = clamp_count_to_pool(DEFAULT_PICK_COUNT, len(candidates))

    graph = build_graph()
    initial_state = {
        "input": (
            "I'm looking for new sneakers to add to my collection. "
            "I prefer Jordan. I like Grey colorways."
        ),
        "user_name": "cli_test_user",
        "requested_brands": brands,
        "requested_colors": colors,
    }

    final_state = {}
    for chunk in graph.stream(initial_state, stream_mode="updates"):
        for _, updates in chunk.items():
            final_state.update(updates)

    proposed = final_state.get("proposed_sneakers", [])

    off_brand = [
        name for name in proposed
        if SNEAKER_CATALOG.get(name, {}).get("brand", "").lower() not in {b.lower() for b in brands}
    ]
    check(
        not off_brand,
        "every proposed pick matches the requested brand (Jordan)",
        f"off-brand picks: {off_brand}",
    )

    check(
        len(proposed) == expected_count,
        f"proposed count matches the expected default ({expected_count})",
        f"got {len(proposed)}: {proposed}",
    )


def main():
    """
    main
    ----
    Runs every test group, prints a summary, and exits with status 1 if any
    test failed so the harness can gate a CI pipeline.

    Returns:
        None. Calls sys.exit with the appropriate code.
    """
    print("=" * 60)
    print("Sneaker Agent — CLI test harness")
    print("=" * 60)
    if HAS_REAL_KEY:
        print("GOOGLE_API_KEY detected — live pipeline test will run.")
    else:
        print("No GOOGLE_API_KEY — live pipeline test will be skipped.")

    test_reasoning_parser()
    test_catalog_filter()
    test_user_routes()
    test_database_helpers()
    test_selection_logic()
    test_bid_validation()
    test_full_pipeline()
    test_bid_fairness_judgment()
    test_brand_and_count_compliance()

    passed = sum(1 for _, status, _ in RESULTS if status == "PASS")
    failed = sum(1 for _, status, _ in RESULTS if status == "FAIL")
    skipped = sum(1 for _, status, _ in RESULTS if status == "SKIP")

    print("\n" + "=" * 60)
    print(f"Summary: {passed} passed, {failed} failed, {skipped} skipped")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
