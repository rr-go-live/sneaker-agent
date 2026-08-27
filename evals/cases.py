"""
cases.py
--------
Test case definitions for the sneaker agent eval harness.

Each test case is a plain dict with two sections:
  - Input fields:   what to send through the pipeline (input, user_name)
  - Expectation fields: what we expect the system to do

A "kind" field controls how runner.py executes the case:
  kind = "graph" (default, can be omitted) — runs the full LangGraph
         pipeline (orchestrator → ... ) via app.stream()
  kind = "bid"   — calls agents.bid_agent.evaluate_bid() directly, since
         bidding is a standalone flow outside the graph (one already-known
         sneaker + a dollar amount, not a routing decision)

Expectation fields used by scorers:
  expected_first_agent     (str|None)  — which agent orchestrator should pick first (graph only)
  expect_proposed_sneakers (bool)      — should sneaker_agent produce picks? (graph only)
  expected_pick_included   (str|None)  — a specific catalog name that must appear
                                         in proposed_sneakers (graph only)
  expected_constraints     (dict|None) — constraints EVERY pick must satisfy
                                         (graph only). Any of:
                                           brands    (list[str])
                                           profile   (str: low/mid/high)
                                           max_price (float, retail ceiling)
                                           min_year  (int, release-year floor)
  is_failure_case           (bool)     — does this test intentionally hit an error path?
  expected_output_contains  (str|None) — substring the final output must include
  expected_accepted         (bool|None)— for bid cases, whether the bid should be accepted

A stated price ceiling is a filter on what the shopper said they'd spend —
not a revival of the removed budget-agent concept. Nothing here looks up or
enforces an account balance; "under $150" is just another constraint, the
same as a brand or a colorway.

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

    # ------------------------------------------------------------------
    # TC-008: Bid far below market — should be rejected
    # Standalone flow: bid_agent.evaluate_bid() directly, no graph
    # ------------------------------------------------------------------
    {
        "id":                 "TC-008",
        "name":               "Lowball bid rejected",
        "description":        "A bid far below retail/market/lowest-ask should be rejected by the fairness judgment",
        "kind":               "bid",
        "input":              "Bid $50.00 on Jordan 4 Retro SB Pine Green",
        "sneaker_name":       "Jordan 4 Retro SB Pine Green",
        "bid_amount":         50.0,
        "user_name":          "John",
        "expected_accepted":  False,
        "is_failure_case":    False,
        "expected_output_contains": None,
    },

    # ------------------------------------------------------------------
    # TC-009: Bid near lowest ask — should be accepted
    # ------------------------------------------------------------------
    {
        "id":                 "TC-009",
        "name":               "Fair bid accepted",
        "description":        "A bid close to the lowest ask should be accepted by the fairness judgment",
        "kind":               "bid",
        "input":              "Bid $320.00 on Jordan 4 Retro SB Pine Green",
        "sneaker_name":       "Jordan 4 Retro SB Pine Green",
        "bid_amount":         320.0,
        "user_name":          "John",
        "expected_accepted":  True,
        "is_failure_case":    False,
        "expected_output_contains": None,
    },

    # ------------------------------------------------------------------
    # TC-010: Bid on a nonexistent sneaker — deterministic rejection
    # No LLM call — validate_bid_request() rejects before evaluate_bid ever asks
    # ------------------------------------------------------------------
    {
        "id":                 "TC-010",
        "name":               "Bid on unknown sneaker rejected",
        "description":        "A bid on a sneaker that isn't in the catalog must be rejected deterministically, without an LLM call",
        "kind":               "bid",
        "input":              "Bid $500.00 on Definitely Not A Real Sneaker XYZ",
        "sneaker_name":       "Definitely Not A Real Sneaker XYZ",
        "bid_amount":         500.0,
        "user_name":          "John",
        "expected_accepted":  False,
        "is_failure_case":    True,
        "expected_output_contains": "not a real catalog item",
    },

    # ------------------------------------------------------------------
    # TC-011: Highest retail value Jordans post-2022
    #
    # Was a documented known-limitation case: with no date filter and no
    # retail sort, candidates were ranked by popularity and capped at
    # MAX_CATALOG_SIZE, so "Jordan 1 Low SE True Blue" ($1,110 retail,
    # released 2022-06-22) — rank #197 of 538 in-stock Jordans by
    # popularity — never reached the LLM's candidate pool at all.
    #
    # extract_min_release_year + extract_sort_preference + sort_candidates
    # in agents/selection.py closed that gap, and this now passes.
    # ------------------------------------------------------------------
    {
        "id":                    "TC-011",
        "name":                  "Highest retail Jordans post-2022",
        "description":           "A superlative + date query must re-rank the pool by retail price before the MAX_CATALOG_SIZE cap, or the correct answer never reaches the LLM",
        "input":                 "Get me the single highest retail value Jordan released after 2022",
        "user_name":             "John",
        "expected_first_agent":  "sneaker_agent",
        "expect_proposed_sneakers": True,
        "expected_pick_included": "Jordan 1 Low SE True Blue",
        "expected_constraints":  {"brands": ["Jordan"], "min_year": 2022},
        "is_failure_case":       False,
        "expected_output_contains": None,
    },

    # ------------------------------------------------------------------
    # TC-012: Free-text brand + silhouette + price (the reported bug)
    #
    # Regression for the exact query that surfaced this class of failure:
    # the admin Custom Scenario panel sends only a raw string with no
    # structured filter fields, so brand/profile/price had to be parsed
    # from prose. Before extract_requested_brands existed, this returned
    # Nike and adidas picks for a query that plainly said "jordan".
    # ------------------------------------------------------------------
    {
        "id":                    "TC-012",
        "name":                  "Free-text brand + silhouette + budget",
        "description":           "Brand, silhouette and price ceiling named only in prose must all be honored on every pick",
        "input":                 "get me a low top jordan sneaker that I can get with 150 dollars",
        "user_name":             "John",
        "expected_first_agent":  "sneaker_agent",
        "expect_proposed_sneakers": True,
        "expected_constraints":  {"brands": ["Jordan"], "profile": "low", "max_price": 150.0},
        "is_failure_case":       False,
        "expected_output_contains": None,
    },

    # ------------------------------------------------------------------
    # TC-013: Cheapest-superlative query
    # Exercises the opposite sort direction from TC-011.
    # ------------------------------------------------------------------
    {
        "id":                    "TC-013",
        "name":                  "Cheapest New Balance",
        "description":           "An ascending-price superlative must re-rank the pool the other way and still respect the brand filter",
        "input":                 "what is the cheapest New Balance you have",
        "user_name":             "Alice",
        "expected_first_agent":  "sneaker_agent",
        "expect_proposed_sneakers": True,
        "expected_constraints":  {"brands": ["New Balance"]},
        "is_failure_case":       False,
        "expected_output_contains": None,
    },

    # ------------------------------------------------------------------
    # TC-014: Multi-constraint colorway + brand + budget
    # The kind of stacked request a real shopper actually types.
    # ------------------------------------------------------------------
    {
        "id":                    "TC-014",
        "name":                  "Colorway + brand + budget stack",
        "description":           "Several constraints in one sentence must all survive to the final picks",
        "input":                 "I want black Nike low tops under 120 dollars",
        "user_name":             "John",
        "expected_first_agent":  "sneaker_agent",
        "expect_proposed_sneakers": True,
        "expected_constraints":  {"brands": ["Nike"], "profile": "low", "max_price": 120.0},
        "is_failure_case":       False,
        "expected_output_contains": None,
    },

    # ------------------------------------------------------------------
    # TC-015: Impossible constraint — must fail honestly
    #
    # No sneaker in the catalog is a Jordan under $10. The correct
    # behavior is an honest empty result naming the unmet constraints,
    # NOT silently widening the search to something cheaper off-brand.
    # ------------------------------------------------------------------
    {
        "id":                    "TC-015",
        "name":                  "Impossible budget fails honestly",
        "description":           "A constraint nothing satisfies must return an honest empty result rather than silently substituting off-brand or over-budget picks",
        "input":                 "find me a jordan under 10 dollars",
        "user_name":             "John",
        "expected_first_agent":  "sneaker_agent",
        "expect_proposed_sneakers": False,
        "is_failure_case":       True,
        "expected_output_contains": "No in-stock sneakers matched",
    },
]
