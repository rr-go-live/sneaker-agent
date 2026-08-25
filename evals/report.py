"""
report.py
---------
Formats and prints the eval results produced by runner.py.

The report has four sections:
  1. Header       — total cases, pass rate, overall score, total time
  2. Summary table— one line per test case: ID, name, score, latency, PASS/FAIL
  3. Dimension scores — aggregate pass rates grouped by scoring dimension
  4. Details      — per-test breakdown listing every applicable scorer result

Call:
  from evals.report import print_report
  print_report(results)

where results is the list returned by runner.run_all_cases().
"""

LINE_WIDTH = 78
BAR_WIDTH  = 20

DIMENSION_LABELS = {
    "routing":           "Routing Accuracy    ",
    "sneaker_validity":  "Sneaker Validity    ",
    "failure_handling":  "Failure Handling    ",
    "latency":           "Latency             ",
}


def print_report(results):
    """
    print_report
    ------------
    Entry point. Prints the full eval report to stdout.

    Args:
        results (list[dict]): list of RunResult dicts from runner.run_all_cases()

    Returns:
        None
    """
    _print_header(results)
    _print_summary_table(results)
    _print_dimension_scores(results)
    _print_details(results)


# ─────────────────────────────────────────────────────────────────────────────
# Section printers
# ─────────────────────────────────────────────────────────────────────────────

def _print_header(results):
    """
    _print_header
    -------------
    Prints the top-level summary: case count, pass count, total time, score.

    Args:
        results (list[dict]): RunResult list

    Returns:
        None
    """
    total      = len(results)
    passed     = sum(1 for r in results if _case_passed(r))
    avg_score  = sum(r["overall_score"] for r in results) / total if total else 0
    total_time = sum(r["total_latency"] for r in results)

    print()
    print("=" * LINE_WIDTH)
    print("  SNEAKER AGENT — EVAL REPORT")
    print("=" * LINE_WIDTH)
    print(
        f"  {total} test cases  |  "
        f"{passed}/{total} passed  |  "
        f"total time: {total_time:.1f}s  |  "
        f"overall score: {avg_score * 100:.0f}%"
    )
    print()


def _print_summary_table(results):
    """
    _print_summary_table
    --------------------
    Prints a one-line-per-case summary table with ID, name, score, time, status.

    Args:
        results (list[dict]): RunResult list

    Returns:
        None
    """
    print("-" * LINE_WIDTH)
    print(f"  {'ID':<8}  {'Test Case':<38}  {'Score':>5}  {'Time':>6}  Status")
    print("-" * LINE_WIDTH)

    for r in results:
        case   = r["test_case"]
        status = "PASS" if _case_passed(r) else "FAIL"
        error  = " [ERROR]" if r.get("error") else ""
        print(
            f"  {case['id']:<8}  {case['name']:<38}  "
            f"{r['overall_score']:>4.0%}  "
            f"{r['total_latency']:>5.1f}s  "
            f"{status}{error}"
        )

    print()


def _print_dimension_scores(results):
    """
    _print_dimension_scores
    -----------------------
    Aggregates scores across all test cases per dimension and prints a bar chart.
    Only dimensions that appeared in at least one test case are shown.

    Args:
        results (list[dict]): RunResult list

    Returns:
        None
    """
    # Collect raw scores per dimension
    dimension_data = {}
    for r in results:
        for dim, score_result in r["scores"].items():
            if dim not in dimension_data:
                dimension_data[dim] = []
            dimension_data[dim].append(score_result["score"])

    print("-" * LINE_WIDTH)
    print("  SCORES BY DIMENSION")
    print("-" * LINE_WIDTH)

    for dim, label in DIMENSION_LABELS.items():
        if dim not in dimension_data:
            continue
        scores     = dimension_data[dim]
        avg        = sum(scores) / len(scores)
        pass_count = sum(1 for s in scores if s >= 1.0)
        bar        = _make_bar(avg)
        print(
            f"  {label}  {bar}  "
            f"{pass_count}/{len(scores)} cases  "
            f"{avg * 100:.0f}%"
        )

    print()


def _print_details(results):
    """
    _print_details
    --------------
    Prints a full breakdown for every test case: agent path, per-node latency,
    and each applicable scorer result with its reason string.

    Args:
        results (list[dict]): RunResult list

    Returns:
        None
    """
    print("-" * LINE_WIDTH)
    print("  DETAILS")
    print("-" * LINE_WIDTH)

    for r in results:
        case   = r["test_case"]
        status = "PASS" if _case_passed(r) else "FAIL"

        print(f"\n  {case['id']}  {case['name']}  [{status}]")
        print(f"  Input:    \"{case['input'][:65]}\"")
        print(f"  User:     {case['user_name']}")
        print(f"  Path:     {' → '.join(r['nodes_visited']) or '(none)'}")

        # Per-node latency breakdown
        if r["node_latencies"]:
            parts = [f"{n}: {t:.2f}s" for n, t in r["node_latencies"].items()]
            print(f"  Timing:   {', '.join(parts)}")

        if r.get("error"):
            print(f"  ERROR:    {r['error']}")

        # Each applicable scorer (latency shown in Timing line above)
        for dim, score_result in r["scores"].items():
            if dim == "latency":
                continue
            label  = DIMENSION_LABELS.get(dim, dim).strip()
            marker = "✓" if score_result["passed"] else "✗"
            print(f"  {label:<22} {marker}  {score_result['reason']}")

        # Snippet of the final output
        output = r["final_state"].get("output", "")
        if output:
            snippet = output.replace("\n", " ")[:100]
            print(f"  Output:   {snippet}...")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _case_passed(run_result):
    """
    _case_passed
    ------------
    A test case passes when there is no exception AND every applicable scorer
    returned passed=True.

    Args:
        run_result (dict): a RunResult from runner.py

    Returns:
        bool
    """
    if run_result.get("error"):
        return False
    return all(s["passed"] for s in run_result["scores"].values())


def _make_bar(score):
    """
    _make_bar
    ---------
    Builds a fixed-width ASCII bar for a 0.0–1.0 score.
    Example: 0.75 → "███████████████░░░░░"

    Args:
        score (float): 0.0 to 1.0

    Returns:
        str
    """
    filled = round(score * BAR_WIDTH)
    empty  = BAR_WIDTH - filled
    return "█" * filled + "░" * empty
