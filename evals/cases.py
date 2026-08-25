"""
cases.py
--------
Test case definitions for the sneaker agent eval harness.

Each test case is a plain dict with two sections:
  - Input fields:   what to send to the agent graph (input, user_name)
  - Expectation fields: what we expect the system to do

Expectation fields used by scorers:
  expected_first_agent    (str|None)  — which agent orchestrator should pick first
  expect_proposed_sneakers (bool)     — should sneaker_agent produce picks?
  is_failure_case          (bool)     — does this test intentionally hit an error path?
  expected_output_contains (str|None) — substring the final output must include

There is no budget concept in this app — sneaker_agent has no price ceiling,
so there's nothing to test for "budget accuracy" or "budget compliance"
anymore. No current test case sets is_failure_case: True either, since
removing the budget requirement also removed the app's only graceful-error
path (an unresolvable budget lookup); the field stays in the schema for
whenever a real failure path exists again.

To add a new test case: append a dict to TEST_CASES using the same keys.
"""

TEST_CASES = [
    # ------------------------------------------------------------------
    # TC-001: Direct shopping request
    # Chain: orchestrator → sneaker_agent → critique_agent → logistics_agent
    # ------------------------------------------------------------------
    {
        "id":                    "TC-001",
        "name":                  "Direct shopping request",
        "description":           "Shopping intent should route to sneaker_agent and produce picks",
        "input":                 "Help me find some fresh kicks to add to my collection",
        "user_name":             "John",
        "expected_first_agent":  "sneaker_agent",
        "expect_proposed_sneakers": True,
        "is_failure_case":       False,
        "expected_output_contains": None,
    },

    # ------------------------------------------------------------------
    # TC-002: Collection check — no shopping intent
    # Chain: orchestrator → inventory_agent → END
    # ------------------------------------------------------------------
    {
        "id":                    "TC-002",
        "name":                  "Collection check only — no shopping",
        "description":           "Asking what you own should route to inventory_agent and stop; no sneaker picks expected",
        "input":                 "What sneakers do I already have in my collection?",
        "user_name":             "Alice",
        "expected_first_agent":  "inventory_agent",
        "expect_proposed_sneakers": False,
        "is_failure_case":       False,
        "expected_output_contains": None,
    },

    # ------------------------------------------------------------------
    # TC-003: Full chain — inventory review then shopping
    # Chain: orchestrator → inventory_agent → sneaker_agent → critique_agent → logistics_agent
    # ------------------------------------------------------------------
    {
        "id":                    "TC-003",
        "name":                  "Inventory review then shopping",
        "description":           "Asking to see owned sneakers AND buy new ones should traverse inventory_agent then sneaker_agent",
        "input":                 "I want to upgrade my sneaker collection. What do I already own, and what new heat can I cop to complete the rotation?",
        "user_name":             "John",
        "expected_first_agent":  "inventory_agent",
        "expect_proposed_sneakers": True,
        "is_failure_case":       False,
        "expected_output_contains": None,
    },

    # ------------------------------------------------------------------
    # TC-004: Style advice — still produces picks
    # Chain: orchestrator → sneaker_agent → critique_agent → logistics_agent
    # ------------------------------------------------------------------
    {
        "id":                    "TC-004",
        "name":                  "Style advice request",
        "description":           "A trend/style question should route to sneaker_agent the same as a direct buying request",
        "input":                 "What are the hottest sneaker styles and trends right now?",
        "user_name":             "John",
        "expected_first_agent":  "sneaker_agent",
        "expect_proposed_sneakers": True,
        "is_failure_case":       False,
        "expected_output_contains": None,
    },

    # ------------------------------------------------------------------
    # TC-005: Specific stock check — routes directly to logistics_agent
    # Chain: orchestrator → logistics_agent → END
    # ------------------------------------------------------------------
    {
        "id":                    "TC-005",
        "name":                  "Stock availability check",
        "description":           "Asking if a specific named sneaker is in stock should route straight to logistics_agent",
        "input":                 "Is the Jordan 4 Retro Infrared available in the store right now?",
        "user_name":             "John",
        "expected_first_agent":  "logistics_agent",
        "expect_proposed_sneakers": False,
        "is_failure_case":       False,
        "expected_output_contains": None,
    },

    # ------------------------------------------------------------------
    # TC-006: Second user — routing consistency
    # Chain: orchestrator → sneaker_agent → critique_agent → logistics_agent
    # ------------------------------------------------------------------
    {
        "id":                    "TC-006",
        "name":                  "Alice shopping request",
        "description":           "Confirms shopping-intent routing holds for a different user, not just John",
        "input":                 "I want to buy some new heat for my collection",
        "user_name":             "Alice",
        "expected_first_agent":  "sneaker_agent",
        "expect_proposed_sneakers": True,
        "is_failure_case":       False,
        "expected_output_contains": None,
    },

    # ------------------------------------------------------------------
    # TC-007: Minimal one-word query — system should not crash
    # Chain: any valid route without error
    # ------------------------------------------------------------------
    {
        "id":                    "TC-007",
        "name":                  "Minimal query — no crash",
        "description":           "Even a vague one-word query should produce some output without an exception",
        "input":                 "sneakers",
        "user_name":             "John",
        "expected_first_agent":  None,
        "expect_proposed_sneakers": False,
        "is_failure_case":       False,
        "expected_output_contains": None,
    },
]
