"""
scorers.py
----------
Individual scoring functions for the eval harness.

Each function takes a run_result dict (produced by runner.py for one test case)
and returns either:

  A ScoreResult dict:
    {
      "passed": bool,    — True if the check passed
      "score":  float,   — 0.0 to 1.0  (1.0 = perfect)
      "reason": str,     — plain-English explanation
    }

  Or None — meaning this scorer does not apply to the given test case and
  should be excluded from that case's overall score.

There are six scorers, each targeting one eval dimension:

  1. score_routing          — Did the orchestrator pick the right first agent? (graph cases)
  2. score_sneaker_validity — Did sneaker_agent avoid hallucinating names? (graph cases)
  3. score_expected_pick    — Did a specific expected catalog name show up in the picks? (graph cases)
  4. score_bid_outcome      — Did bid_agent accept/reject as expected? (bid cases)
  5. score_failure_handling — Did an error path fail gracefully (no crash)?
  6. score_latency          — Did the full run finish fast enough?

There is no account-budget scoring — no balance is tracked, so there's
nothing to check a budget lookup or spend compliance against. A price
ceiling the shopper states themselves is checked by score_constraint_compliance.
"""

from data.catalog import SNEAKER_CATALOG

# Latency thresholds in seconds
# A 2-LLM-call chain (orchestrator + one specialist) typically runs 5–12s.
# A 4-agent chain with 3 LLM calls can reach 20s. Thresholds reflect this.
LATENCY_PASS_SECONDS = 15.0
LATENCY_WARN_SECONDS = 30.0


def score_routing(run_result):
    """
    score_routing
    -------------
    Checks whether the orchestrator's LLM routing decision matches the expected
    first agent. This validates that the model correctly interprets user intent
    and dispatches to the right specialist.

    Skipped when expected_first_agent is None (test case does not check routing).

    Args:
        run_result (dict): a RunResult produced by runner.py

    Returns:
        dict | None: ScoreResult, or None if not applicable
    """
    expected = run_result["test_case"].get("expected_first_agent")
    if expected is None:
        return None

    nodes_visited = run_result["nodes_visited"]

    # Find orchestrator in the visit list and read the node that follows it
    for i, node in enumerate(nodes_visited):
        if node == "orchestrator":
            if i + 1 >= len(nodes_visited):
                return {
                    "passed": False,
                    "score":  0.0,
                    "reason": "orchestrator ran but no agent followed",
                }
            actual = nodes_visited[i + 1]
            passed = actual == expected
            return {
                "passed": passed,
                "score":  1.0 if passed else 0.0,
                "reason": (
                    f"routed to '{actual}'"
                    + (" ✓" if passed else f"  (expected '{expected}')")
                ),
            }

    return {
        "passed": False,
        "score":  0.0,
        "reason": "orchestrator node was never visited",
    }


def score_sneaker_validity(run_result):
    """
    score_sneaker_validity
    ----------------------
    Checks whether every sneaker name proposed by sneaker_agent actually exists
    in SNEAKER_CATALOG. This catches LLM hallucination — if the model invented
    a name, it won't match any catalog key and lowers the score.

    Score = valid_picks / total_picks  (partial credit for partial hallucination)

    Skipped when expect_proposed_sneakers is False.

    Args:
        run_result (dict): a RunResult produced by runner.py

    Returns:
        dict | None: ScoreResult, or None if not applicable
    """
    if not run_result["test_case"].get("expect_proposed_sneakers"):
        return None

    proposed = run_result["final_state"].get("proposed_sneakers", [])

    if len(proposed) == 0:
        return {
            "passed": False,
            "score":  0.0,
            "reason": "expected sneaker picks but none were proposed",
        }

    valid   = [s for s in proposed if s in SNEAKER_CATALOG]
    invalid = [s for s in proposed if s not in SNEAKER_CATALOG]
    score   = len(valid) / len(proposed)
    passed  = score == 1.0

    if passed:
        reason = f"all {len(valid)} picks are real catalog items ✓"
    else:
        reason = f"{len(valid)}/{len(proposed)} valid — hallucinated: {invalid}"

    return {"passed": passed, "score": score, "reason": reason}


def score_expected_pick(run_result):
    """
    score_expected_pick
    --------------------
    Checks whether a specific catalog name the test case names as
    'expected_pick_included' actually appears among proposed_sneakers.
    Unlike score_sneaker_validity (which only checks picks aren't
    hallucinated), this checks the pipeline found the *right* pick —
    useful for regression-testing an attribute-based query (e.g. "highest
    retail value") where any in-stock sneaker would pass validity but
    only one is the actually-correct answer.

    Skipped when the test case doesn't set expected_pick_included.

    Args:
        run_result (dict): a RunResult produced by runner.py

    Returns:
        dict | None: ScoreResult, or None if not applicable
    """
    expected = run_result["test_case"].get("expected_pick_included")
    if expected is None:
        return None

    proposed = run_result["final_state"].get("proposed_sneakers", [])
    passed   = expected in proposed

    return {
        "passed": passed,
        "score":  1.0 if passed else 0.0,
        "reason": (
            f"'{expected}' is among the picks ✓" if passed else
            f"'{expected}' was expected but not proposed — picks were: {proposed}"
        ),
    }


def score_constraint_compliance(run_result):
    """
    score_constraint_compliance
    ----------------------------
    Checks that EVERY proposed pick actually satisfies the constraints the
    user stated in free text — brand, silhouette, retail ceiling, release
    year. This is the end-to-end guard for the whole free-text extraction
    path: routing can be right and every name can be real while the picks
    still ignore what the shopper plainly asked for.

    Reads 'expected_constraints' from the test case, a dict with any of:
      brands    (list[str]) — every pick's brand must be one of these
      profile   (str)       — every pick must have this silhouette
      max_price (float)     — every pick's retail must be at or under this
      min_year  (int)       — every pick must have released in/after this

    Score is the fraction of picks satisfying all stated constraints, so a
    partial violation scores partially rather than all-or-nothing.

    Skipped when the test case sets no expected_constraints.

    Args:
        run_result (dict): a RunResult produced by runner.py

    Returns:
        dict | None: ScoreResult, or None if not applicable
    """
    constraints = run_result["test_case"].get("expected_constraints")
    if not constraints:
        return None

    proposed = run_result["final_state"].get("proposed_sneakers", [])
    if len(proposed) == 0:
        return {
            "passed": False,
            "score":  0.0,
            "reason": "expected constrained picks but none were proposed",
        }

    wanted_brands = [b.lower() for b in constraints.get("brands", [])]
    wanted_profile = constraints.get("profile")
    max_price      = constraints.get("max_price")
    min_year       = constraints.get("min_year")

    compliant  = []
    violations = []

    for name in proposed:
        details = SNEAKER_CATALOG.get(name)
        if details is None:
            violations.append(f"{name} (not in catalog)")
            continue

        failed_checks = []

        if wanted_brands and details.get("brand", "").lower() not in wanted_brands:
            failed_checks.append(f"brand={details.get('brand')}")

        if wanted_profile and details.get("profile", "").lower() != wanted_profile.lower():
            failed_checks.append(f"profile={details.get('profile')}")

        if max_price is not None:
            retail = details.get("retail_price")
            if retail is None or retail > max_price:
                failed_checks.append(f"retail=${retail}")

        if min_year is not None:
            release_date = details.get("release_date") or ""
            year_text = release_date[:4]
            if not year_text.isdigit() or int(year_text) < min_year:
                failed_checks.append(f"released={release_date or 'unknown'}")

        if failed_checks:
            violations.append(f"{name} ({', '.join(failed_checks)})")
        else:
            compliant.append(name)

    score  = len(compliant) / len(proposed)
    passed = score == 1.0

    if passed:
        reason = f"all {len(compliant)} picks satisfy every stated constraint ✓"
    else:
        reason = (
            f"{len(compliant)}/{len(proposed)} picks compliant — violations: "
            + "; ".join(violations)
        )

    return {"passed": passed, "score": score, "reason": reason}


def score_bid_outcome(run_result):
    """
    score_bid_outcome
    ------------------
    Checks whether bid_agent's accept/reject decision matches the test
    case's expected_accepted. Only applies to bid-kind test cases.

    Skipped when the test case doesn't set expected_accepted (e.g. every
    graph-kind test case, or a bid case with no fixed expectation).

    Args:
        run_result (dict): a RunResult produced by runner.py

    Returns:
        dict | None: ScoreResult, or None if not applicable
    """
    expected = run_result["test_case"].get("expected_accepted")
    if expected is None:
        return None

    actual = run_result["final_state"].get("accepted")
    passed = actual == expected

    return {
        "passed": passed,
        "score":  1.0 if passed else 0.0,
        "reason": (
            f"bid {'accepted' if actual else 'rejected'} as expected ✓" if passed else
            f"expected {'accepted' if expected else 'rejected'}, got "
            f"{'accepted' if actual else 'rejected'}"
        ),
    }


def score_failure_handling(run_result):
    """
    score_failure_handling
    ----------------------
    Only runs for test cases marked is_failure_case: True. Checks two things:
      1. The system did not raise an uncaught exception (no crash)
      2. The output contains a recognizable, user-friendly error message

    If the system crashes (runner.py captures exceptions in run_result["error"]),
    this scorer returns 0.0 regardless of the expected text.

    Args:
        run_result (dict): a RunResult produced by runner.py

    Returns:
        dict | None: ScoreResult, or None if not a failure test case
    """
    if not run_result["test_case"].get("is_failure_case"):
        return None

    # A raised exception means the system crashed instead of failing gracefully
    if run_result.get("error"):
        return {
            "passed": False,
            "score":  0.0,
            "reason": f"system raised an exception: {run_result['error']}",
        }

    output = run_result["final_state"].get("output", "")

    if not output:
        return {
            "passed": False,
            "score":  0.0,
            "reason": "failure case produced no output at all",
        }

    expected_text = run_result["test_case"].get("expected_output_contains") or ""

    if expected_text and expected_text.lower() not in output.lower():
        return {
            "passed": False,
            "score":  0.5,
            "reason": f"output exists but missing expected text: '{expected_text}'",
        }

    return {
        "passed": True,
        "score":  1.0,
        "reason": "graceful error message returned ✓",
    }


def score_latency(run_result):
    """
    score_latency
    -------------
    Scores the total wall-clock time from start to finish for one test case run.

    Thresholds:
      < LATENCY_PASS_SECONDS (15s) → score 1.0  (pass — fast)
      < LATENCY_WARN_SECONDS (30s) → score 0.5  (warn — slow but acceptable)
      >= LATENCY_WARN_SECONDS       → score 0.0  (fail — too slow)

    Args:
        run_result (dict): a RunResult produced by runner.py

    Returns:
        dict: ScoreResult (always returned — latency applies to every test case)
    """
    elapsed = run_result.get("total_latency", 0.0)

    if elapsed < LATENCY_PASS_SECONDS:
        return {"passed": True,  "score": 1.0, "reason": f"{elapsed:.2f}s ✓"}
    elif elapsed < LATENCY_WARN_SECONDS:
        return {"passed": True,  "score": 0.5, "reason": f"{elapsed:.2f}s (slow)"}
    else:
        return {"passed": False, "score": 0.0, "reason": f"{elapsed:.2f}s (too slow)"}
