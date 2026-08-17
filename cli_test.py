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


def test_full_pipeline():
    """
    test_full_pipeline
    ------------------
    Runs the complete multi-agent graph for a buying request and confirms
    that every node emits reasoning, the sneaker agent proposes picks, and
    the picks respect the supplied budget.

    Skipped when no real GOOGLE_API_KEY is configured, since it makes live
    Gemini calls.

    Returns:
        None. Records one result per assertion, or a single SKIP.
    """
    print("\nFull multi-agent pipeline")

    if not HAS_REAL_KEY:
        record("full pipeline", "SKIP", "no GOOGLE_API_KEY configured")
        return

    from data.catalog import SNEAKER_CATALOG
    from graph import build_graph

    graph = build_graph()
    budget = 300.0
    initial_state = {
        "input": "I want a clean white low-top for everyday wear that holds resale value",
        "user_name": "cli_test_user",
        "budget": budget,
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

    total_retail = 0.0
    for name in proposed:
        details = SNEAKER_CATALOG.get(name, {})
        total_retail += details.get("retail_price", 0)

    check(
        total_retail <= budget,
        "proposed picks stay within the budget",
        f"total_retail={total_retail} budget={budget}",
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
    test_full_pipeline()

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
