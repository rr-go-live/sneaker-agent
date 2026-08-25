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

There are four scorers, each targeting one eval dimension:

  1. score_routing          — Did the orchestrator pick the right first agent?
  2. score_sneaker_validity — Did sneaker_agent avoid hallucinating names?
  3. score_failure_handling — Did an error path fail gracefully (no crash)?
  4. score_latency          — Did the full run finish fast enough?

There is no budget scoring — the app has no price ceiling, so there's
nothing to check a budget lookup or spend compliance against.
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
      < 5s   → score 1.0  (pass — fast)
      5–10s  → score 0.5  (warn — slow but acceptable)
      > 10s  → score 0.0  (fail — too slow)

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
