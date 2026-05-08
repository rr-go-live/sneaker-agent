"""
cases.py
--------
Test case definitions for the sneaker agent eval harness.

Each test case is a plain dict with two sections:
  - Input fields:   what to send to the agent graph (input, user_name)
  - Expectation fields: what we expect the system to do

Expectation fields used by scorers:
  expected_first_agent    (str|None)  — which agent orchestrator should pick first
  expected_budget         (float|None)— budget that financial_agent should find
  expect_proposed_sneakers (bool)     — should sneaker_agent produce picks?
  check_budget_compliance  (bool)     — should proposed picks stay under budget?
  is_failure_case          (bool)     — does this test intentionally hit an error path?
  expected_output_contains (str|None) — substring the final output must include

To add a new test case: append a dict to TEST_CASES using the same keys.
"""

TEST_CASES = [
    # ------------------------------------------------------------------
    # TC-001: Direct shopping request
    # Chain: orchestrator → financial_agent → sneaker_agent → logistics_agent
    # ------------------------------------------------------------------
    {
        "id":                    "TC-001",
        "name":                  "Direct shopping request",
        "description":           "Shopping intent should route to financial_agent first, then produce sneaker picks within John's $300 budget",
        "input":                 "Help me find some fresh kicks to add to my collection",
        "user_name":             "John",
        "expected_first_agent":  "financial_agent",
        "expected_budget":       300.0,
        "expect_proposed_sneakers": True,
        "check_budget_compliance":  True,
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
        "expected_budget":       None,
        "expect_proposed_sneakers": False,
        "check_budget_compliance":  False,
        "is_failure_case":       False,
        "expected_output_contains": None,
    },

    # ------------------------------------------------------------------
    # TC-003: Full 4-agent chain
    # Chain: orchestrator → inventory_agent → financial_agent → sneaker_agent → logistics_agent
    # ------------------------------------------------------------------
    {
        "id":                    "TC-003",
        "name":                  "Full 4-agent upgrade chain",
        "description":           "Asking to see owned sneakers AND buy new ones should traverse all 4 agents",
        "input":                 "I want to upgrade my sneaker collection. What do I already own, and what new heat can I cop to complete the rotation within budget?",
        "user_name":             "John",
        "expected_first_agent":  "inventory_agent",
        "expected_budget":       300.0,
        "expect_proposed_sneakers": True,
        "check_budget_compliance":  True,
        "is_failure_case":       False,
        "expected_output_contains": None,
    },

    # ------------------------------------------------------------------
    # TC-004: Style advice only — no buying intent
    # Chain: orchestrator → sneaker_agent → logistics_agent
    # ------------------------------------------------------------------
    {
        "id":                    "TC-004",
        "name":                  "Style advice — no buying intent",
        "description":           "A trend/style question with no purchase intent should skip financial_agent and go straight to sneaker_agent",
        "input":                 "What are the hottest sneaker styles and trends right now?",
        "user_name":             "John",
        "expected_first_agent":  "sneaker_agent",
        "expected_budget":       None,
        "expect_proposed_sneakers": False,
        "check_budget_compliance":  False,
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
        "expected_budget":       None,
        "expect_proposed_sneakers": False,
        "check_budget_compliance":  False,
        "is_failure_case":       False,
        "expected_output_contains": None,
    },

    # ------------------------------------------------------------------
    # TC-006: Unknown user — graceful failure
    # Chain: orchestrator → financial_agent → END (with error message)
    # ------------------------------------------------------------------
    {
        "id":                    "TC-006",
        "name":                  "Unknown user — graceful failure",
        "description":           "A user not in USER_BUDGETS should get a clear error message, not a crash",
        "input":                 "Help me find some cool sneakers",
        "user_name":             "Bob",
        "expected_first_agent":  "financial_agent",
        "expected_budget":       None,
        "expect_proposed_sneakers": False,
        "check_budget_compliance":  False,
        "is_failure_case":       True,
        "expected_output_contains": "could not find a budget",
    },

    # ------------------------------------------------------------------
    # TC-007: Alice shopping — higher budget unlocks more options
    # Chain: orchestrator → financial_agent → sneaker_agent → logistics_agent
    # ------------------------------------------------------------------
    {
        "id":                    "TC-007",
        "name":                  "Alice shopping — $500 budget",
        "description":           "Alice's $500 budget should be retrieved correctly and all picks must stay within it",
        "input":                 "I want to buy some new heat for my collection",
        "user_name":             "Alice",
        "expected_first_agent":  "financial_agent",
        "expected_budget":       500.0,
        "expect_proposed_sneakers": True,
        "check_budget_compliance":  True,
        "is_failure_case":       False,
        "expected_output_contains": None,
    },

    # ------------------------------------------------------------------
    # TC-008: Minimal one-word query — system should not crash
    # Chain: any valid route without error
    # ------------------------------------------------------------------
    {
        "id":                    "TC-008",
        "name":                  "Minimal query — no crash",
        "description":           "Even a vague one-word query should produce some output without an exception",
        "input":                 "sneakers",
        "user_name":             "John",
        "expected_first_agent":  None,
        "expected_budget":       None,
        "expect_proposed_sneakers": False,
        "check_budget_compliance":  False,
        "is_failure_case":       False,
        "expected_output_contains": None,
    },
]
