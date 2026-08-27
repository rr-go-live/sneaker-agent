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


def test_orchestrator_collection_routing():
    """
    test_orchestrator_collection_routing
    --------------------------------------
    Regression test for a real bug: the orchestrator's LLM routing call
    consistently (5/5 runs, not flaky) sent a compound request — one that
    both references the existing collection AND asks for new picks — to
    sneaker_agent, skipping inventory_agent entirely. Its prompt calls
    sneaker_agent "the default for anything sneaker-related," which biases
    it away from inventory_agent whenever shopping language is present at
    all, and it has no rule for handling both intents in one message.

    _mentions_existing_collection() closes this deterministically: matching
    text routes straight to inventory_agent without an LLM call, and
    inventory_agent's own downstream check hands off to sneaker_agent if it
    detects shopping intent too — so a compound request still reaches
    sneaker_agent, just via inventory_agent first.

    Pure function — no LLM calls, so this covers the routing decision
    without depending on live model output.

    Returns:
        None. Records one result per assertion.
    """
    print("\nOrchestrator collection routing (deterministic pre-check)")
    from orchestrator import _mentions_existing_collection

    # Collection references — including the exact TC-003 regression input —
    # must all route to inventory_agent regardless of shopping language
    # also present in the same message.
    collection_cases = [
        "I want to upgrade my sneaker collection. What do I already own, "
        "and what new heat can I cop to complete the rotation?",
        "What sneakers do I already have in my collection?",
        "What do I own?",
        "what is in my collection",
        "see my collection",
        "check my current collection",
    ]
    for text in collection_cases:
        check(
            _mentions_existing_collection(text) is True,
            f"detects a collection reference in {text[:50]!r}...",
        )

    # Pure shopping requests that happen to use the word "collection" as
    # their target ("add to my collection") must NOT trigger this — they
    # are not asking what's already owned.
    shopping_cases = [
        "Help me find some fresh kicks to add to my collection",
        "I want to buy some new heat for my collection",
        "give me a new addition to my collection please",
        "What are the hottest sneaker styles and trends right now?",
        "Is the Jordan 4 Retro Infrared available in the store right now?",
        "sneakers",
    ]
    for text in shopping_cases:
        check(
            _mentions_existing_collection(text) is False,
            f"does not false-positive on {text[:50]!r}...",
        )


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


def test_query_understanding():
    """
    test_query_understanding
    -------------------------
    Pure-function tests for the free-text constraint extractors in
    agents/selection.py — the layer that reads brand, color, silhouette,
    price ceiling, release year and sort preference out of a sentence.

    These exist because a constraint can reach the agent two ways: as a
    structured field from the Advisor UI's filter chips, or named in prose
    ("a low top jordan under $150") from the free-text box, the admin
    Custom Scenario panel, or the CLI. Only the structured path used to be
    honored, so a brand named in prose was dropped — and the prompt then
    told the LLM to favor brand variety, steering it away from what the user
    actually asked for.

    Covers the realistic ways a shopper phrases a request, plus the
    false-positive traps that a naive number/keyword grab would fall into.

    No LLM or database calls — fast and fully deterministic.

    Returns:
        None. Records one result per assertion.
    """
    print("\nQuery understanding (free-text constraint extraction)")
    from agents.selection import (
        extract_requested_brands, extract_requested_colors, extract_profile,
        extract_max_price, extract_min_release_year, extract_sort_preference,
    )

    # A stand-in brand vocabulary; the real call passes the catalog's brands.
    brands = {"Jordan", "Nike", "adidas", "New Balance", "ASICS"}

    # ── Brand ────────────────────────────────────────────────────────────
    check(
        extract_requested_brands("get me a low top jordan", brands) == ["Jordan"],
        "extract_requested_brands: finds a brand named in prose",
    )
    check(
        extract_requested_brands("give me 3 pairs of grey jordans", brands) == ["Jordan"],
        "extract_requested_brands: matches a plural brand mention (jordans)",
    )
    check(
        extract_requested_brands("jordan's are my favorite", brands) == ["Jordan"],
        "extract_requested_brands: matches a possessive brand mention (jordan's)",
    )
    check(
        extract_requested_brands("what's the cheapest new balance", brands) == ["New Balance"],
        "extract_requested_brands: matches a multi-word brand as a phrase",
    )
    check(
        extract_requested_brands("no jordans please, show me something else", brands) == [],
        "extract_requested_brands: a negated brand ('no jordans') is not treated as a filter",
    )
    check(
        extract_requested_brands("anything but adidas", brands) == [],
        "extract_requested_brands: 'anything but <brand>' is not treated as a filter",
    )
    check(
        extract_requested_brands("I already own nikes, what else should I get", brands) == [],
        "extract_requested_brands: 'I already own <brand>' is not treated as a filter",
    )
    check(
        extract_requested_brands("just show me some sneakers", brands) == [],
        "extract_requested_brands: no brand mentioned returns empty",
    )

    # ── Color and silhouette ─────────────────────────────────────────────
    check(
        extract_requested_colors("red and black colorway") == ["black", "red"],
        "extract_requested_colors: finds multiple colors in one request",
    )
    check(
        extract_profile("I want low tops") == "low",
        "extract_profile: 'low tops' resolves to low",
    )
    check(
        extract_profile("high-top basketball shoes") == "high",
        "extract_profile: hyphenated 'high-top' resolves to high",
    )
    check(
        extract_profile("something comfortable") is None,
        "extract_profile: no silhouette mentioned returns None",
    )

    # ── Price ceiling ────────────────────────────────────────────────────
    price_cases = [
        ("a jordan I can get with 150 dollars", 150.0),
        ("cheap nikes under 100",               100.0),
        ("nothing over $200",                   200.0),
        ("300 dollars max",                     300.0),
        ("I have 250 bucks to spend",           250.0),
        ("budget of 300",                       300.0),
        ("$180 or less",                        180.0),
    ]
    for text, expected in price_cases:
        check(
            extract_max_price(text) == expected,
            f"extract_max_price: parses a ceiling from {text!r}",
            f"got {extract_max_price(text)}, expected {expected}",
        )

    check(
        extract_max_price("sneakers with 3 stripes") is None,
        "extract_max_price: a bare number with no currency marker is not a budget "
        "('3 stripes' must not parse as $3)",
        f"got {extract_max_price('sneakers with 3 stripes')}",
    )
    check(
        extract_max_price("size 10 low tops") is None,
        "extract_max_price: a shoe size is not mistaken for a budget",
        f"got {extract_max_price('size 10 low tops')}",
    )

    # ── Release year ─────────────────────────────────────────────────────
    check(
        extract_min_release_year("jordans released after 2022") == 2022,
        "extract_min_release_year: parses 'after <year>'",
    )
    check(
        extract_min_release_year("new balance releases from 2023 onwards") == 2023,
        "extract_min_release_year: parses 'from <year> onwards'",
    )
    check(
        extract_min_release_year("something classic") is None,
        "extract_min_release_year: no year mentioned returns None",
    )

    # ── Sort preference ──────────────────────────────────────────────────
    check(
        extract_sort_preference("the most expensive adidas") == "retail_desc",
        "extract_sort_preference: 'most expensive' sorts by retail descending",
    )
    check(
        extract_sort_preference("highest retail value jordan") == "retail_desc",
        "extract_sort_preference: 'highest retail value' sorts by retail descending",
    )
    check(
        extract_sort_preference("the cheapest new balance") == "retail_asc",
        "extract_sort_preference: 'cheapest' sorts by retail ascending",
    )
    check(
        extract_sort_preference("300 dollars max") is None,
        "extract_sort_preference: a price ceiling ('300 dollars max') is not a "
        "request for the most expensive shoe",
        f"got {extract_sort_preference('300 dollars max')}",
    )
    check(
        extract_sort_preference("find me some sneakers") is None,
        "extract_sort_preference: an open-ended request keeps the default popularity order",
    )


def test_constraint_filters():
    """
    test_constraint_filters
    ------------------------
    Pure-function tests for the deterministic filters that apply the
    extracted constraints to the candidate pool, plus the ordering step.

    The ordering test matters more than it looks: the pool is capped at
    MAX_CATALOG_SIZE before the LLM sees it, so if a superlative query
    isn't re-sorted first, the correct answer can sit outside the window
    and never reach the model at all.

    No LLM or database calls — fast and fully deterministic.

    Returns:
        None. Records one result per assertion.
    """
    print("\nConstraint filters (profile, price, release year, ordering)")
    from agents.selection import (
        filter_by_profile, filter_by_max_price, filter_by_release_year,
        sort_candidates,
    )

    candidates = [
        ("Cheap Low",   {"profile": "low",  "retail_price": 90.0,   "release_date": "2021-05-01", "sales_this_period": 500}),
        ("Mid Range",   {"profile": "low",  "retail_price": 150.0,  "release_date": "2023-01-15", "sales_this_period": 100}),
        ("Pricey High", {"profile": "high", "retail_price": 1110.0, "release_date": "2022-06-22", "sales_this_period": 5}),
        ("No Date",     {"profile": "low",  "retail_price": 120.0,                                 "sales_this_period": 50}),
        # 10 real catalog entries carry retail_price 0.0, meaning unknown.
        ("Unknown Price", {"profile": "low", "retail_price": 0.0,   "release_date": "2023-04-01", "sales_this_period": 10}),
    ]

    # ── filter_by_profile ────────────────────────────────────────────────
    check(
        filter_by_profile(candidates, None) == candidates,
        "filter_by_profile: no profile requested returns candidates unchanged",
    )
    names = [n for n, _ in filter_by_profile(candidates, "high")]
    check(
        names == ["Pricey High"],
        "filter_by_profile: filters to only the requested silhouette",
        f"got {names}",
    )
    check(
        filter_by_profile(candidates, "mid") == [],
        "filter_by_profile: a silhouette with zero matches returns empty, never a substitute",
    )

    # ── filter_by_max_price ──────────────────────────────────────────────
    names = [n for n, _ in filter_by_max_price(candidates, 150.0)]
    check(
        names == ["Cheap Low", "Mid Range", "No Date"],
        "filter_by_max_price: keeps items at or under the ceiling (inclusive)",
        f"got {names}",
    )
    check(
        filter_by_max_price(candidates, None) == candidates,
        "filter_by_max_price: no ceiling returns candidates unchanged",
    )
    check(
        filter_by_max_price(candidates, 10.0) == [],
        "filter_by_max_price: an unreachable ceiling returns empty rather than the cheapest anyway",
        f"got {[n for n, _ in filter_by_max_price(candidates, 10.0)]}",
    )
    names = [n for n, _ in filter_by_max_price(candidates, 200.0)]
    check(
        "Unknown Price" not in names,
        "filter_by_max_price: retail_price 0 means unknown, not free — it must not "
        "satisfy an arbitrary ceiling",
        f"got {names}",
    )

    # ── filter_by_release_year ───────────────────────────────────────────
    names = [n for n, _ in filter_by_release_year(candidates, 2022)]
    check(
        names == ["Mid Range", "Pricey High", "Unknown Price"],
        "filter_by_release_year: keeps only items released in or after the given year",
        f"got {names}",
    )
    check(
        "No Date" not in names,
        "filter_by_release_year: an item with no release date is excluded, not assumed to match",
    )

    # ── sort_candidates ──────────────────────────────────────────────────
    names = [n for n, _ in sort_candidates(candidates, "retail_desc")]
    check(
        names[0] == "Pricey High",
        "sort_candidates: retail_desc puts the highest retail price first",
        f"got {names}",
    )
    names = [n for n, _ in sort_candidates(candidates, "retail_asc")]
    check(
        names[0] == "Cheap Low",
        "sort_candidates: retail_asc puts the lowest retail price first",
        f"got {names}",
    )
    check(
        names[-1] == "Unknown Price",
        "sort_candidates: retail_asc sorts an unknown price (0) last, so "
        "'the cheapest' is never an item whose price nobody knows",
        f"got {names}",
    )
    names = [n for n, _ in sort_candidates(candidates, None)]
    check(
        names[0] == "Cheap Low",
        "sort_candidates: default orders by popularity (sales_this_period)",
        f"got {names}",
    )
    original = list(candidates)
    sort_candidates(candidates, "retail_desc")
    check(
        candidates == original,
        "sort_candidates: does not mutate the caller's list",
    )


def test_availability_report():
    """
    test_availability_report
    -------------------------
    Tests the plain-text shaping of logistics_agent's availability report.

    The agent emits its report in two shapes: structured rows the web UI
    renders as a table, and this text version for the CLI and eval report,
    which have no table to render into. Neither includes the raw StockX URL.

    Pure function — no LLM or database calls.

    Returns:
        None. Records one result per assertion.
    """
    print("\nAvailability report (plain-text shaping)")
    from agents.logistics_agent import _format_report_text

    rows = [
        {"name": "Jordan 4 Retro SB Pine Green", "brand": "Jordan", "in_stock": True,
         "quantity": 2, "retail": 225.0, "market": 388.0,
         "link": "https://stockx.com/jordan-4-retro-sb-pine-green", "found": True},
        {"name": "Nike Dunk Low", "brand": "Nike", "in_stock": False,
         "quantity": 0, "retail": 110.0, "market": 96.0,
         "link": "https://stockx.com/nike-dunk-low", "found": True},
        {"name": "Not A Real Shoe", "brand": "", "in_stock": False,
         "quantity": 0, "retail": None, "market": None, "link": None, "found": False},
    ]

    text = _format_report_text(rows, 335.0)

    check(
        "stockx.com" not in text,
        "report text omits the raw StockX URL",
        f"got: {text!r}",
    )
    check(
        "IN STOCK (2)" in text and "OUT OF STOCK" in text,
        "report text shows live stock status per row",
        f"got: {text!r}",
    )
    check(
        "not found in catalog" in text,
        "an unknown sneaker is reported rather than silently dropped",
        f"got: {text!r}",
    )
    check(
        "$335.00" in text,
        "report text includes the estimated retail total",
        f"got: {text!r}",
    )

    # Column alignment: every data row should start its brand column at the
    # same offset, which is what makes the report readable in a terminal.
    data_lines = [
        line for line in text.split("\n")
        if "IN STOCK" in line or "OUT OF STOCK" in line
    ]
    # The "retail $" marker is unambiguous (it appears once per row), so its
    # column offset is a clean way to prove the columns line up.
    offsets = [line.index("retail $") for line in data_lines]
    check(
        len(set(offsets)) == 1,
        "columns align across rows regardless of sneaker name length",
        f"retail column offsets: {offsets}",
    )

    check(
        _format_report_text([], 0.0) == "No sneakers to check availability for.",
        "an empty row list produces a readable message rather than an empty report",
    )


def test_full_pipeline():
    """
    test_full_pipeline
    ------------------
    Runs the complete multi-agent graph for a buying request and confirms
    that every node emits reasoning and the sneaker agent proposes picks.
    This query states no price ceiling, so any in-stock sneaker is a valid
    candidate. Constraint handling is covered by test_query_understanding
    and test_constraint_filters.

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
    from database import get_out_of_stock_names, restock_sneaker
    from agents.bid_agent import evaluate_bid

    sneaker = "Jordan 4 Retro SB Pine Green"
    # This test checks fairness judgment, not real inventory — restock so
    # the result doesn't depend on whatever a prior manual purchase left
    # this sneaker's quantity at in the shared dev database.
    restock_sneaker(sneaker, quantity=1)
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

    test_orchestrator_collection_routing()
    test_reasoning_parser()
    test_catalog_filter()
    test_user_routes()
    test_database_helpers()
    test_selection_logic()
    test_bid_validation()
    test_query_understanding()
    test_constraint_filters()
    test_availability_report()
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
