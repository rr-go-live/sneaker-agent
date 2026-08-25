"""
runner.py
---------
Runs test cases through the LangGraph agent graph and collects results.

For each test case it:
  1. Calls app.stream() with stream_mode="updates" — this yields one chunk per
     agent node as it completes, so we can capture per-node outputs and timing
  2. Merges all node outputs into a final_state dict
  3. Passes the result to every applicable scorer in scorers.py
  4. Returns a RunResult dict that report.py uses to generate the eval report

Agent print statements are suppressed during runs so they don't pollute the
eval output. Pass verbose=True to run_all_cases() to see them.
"""

import io
import time
import contextlib

from graph import build_graph
from evals.cases import TEST_CASES
from evals import scorers as sc


# Maps scorer names to the functions in scorers.py
SCORER_FNS = {
    "routing":           sc.score_routing,
    "sneaker_validity":  sc.score_sneaker_validity,
    "failure_handling":  sc.score_failure_handling,
    "latency":           sc.score_latency,
}


def run_all_cases(cases=None, verbose=False):
    """
    run_all_cases
    -------------
    Builds the LangGraph graph once, then runs every test case through it.
    Building once is important — it avoids re-compiling the graph per case.

    Args:
        cases   (list, optional): test case dicts. Defaults to all TEST_CASES.
        verbose (bool):           if True, agent print statements are shown.

    Returns:
        list[dict]: one RunResult dict per test case, in order
    """
    if cases is None:
        cases = TEST_CASES

    app = build_graph()
    results = []

    for case in cases:
        result = _run_one_case(app, case, verbose=verbose)
        results.append(result)

    return results


def _run_one_case(app, case, verbose=False):
    """
    _run_one_case
    -------------
    Runs one test case through the graph using streaming mode.

    stream_mode="updates" yields one chunk per completed node. Each chunk is:
      {node_name: {state_fields_updated_by_that_node}}

    We record the order nodes ran, what each returned, and how long each took
    by measuring the time between successive chunks.

    Args:
        app     (CompiledGraph): the compiled LangGraph app
        case    (dict):          a test case from cases.py
        verbose (bool):          if True, agent stdout is shown

    Returns:
        dict: RunResult with keys:
          test_case, final_state, nodes_visited, node_outputs,
          node_latencies, total_latency, agent_logs, scores,
          overall_score, error
    """
    input_data = {
        "input":     case["input"],
        "user_name": case["user_name"],
    }

    nodes_visited  = []   # order agents ran, e.g. ["orchestrator", "sneaker_agent", ...]
    node_outputs   = {}   # {node_name: state_updates_dict}
    node_latencies = {}   # {node_name: seconds_float}
    final_state    = {}   # merged final state built from all node updates
    error          = None

    log_buffer = io.StringIO()
    run_start  = time.time()
    last_tick  = run_start

    try:
        redirect = contextlib.redirect_stdout(log_buffer if not verbose else None)
        with (redirect if not verbose else contextlib.nullcontext()):
            for chunk in app.stream(input_data, stream_mode="updates"):
                now = time.time()
                for node_name, updates in chunk.items():
                    node_latencies[node_name] = round(now - last_tick, 3)
                    node_outputs[node_name]   = updates
                    nodes_visited.append(node_name)
                    final_state.update(updates)
                last_tick = now
    except Exception as exc:
        error = str(exc)

    total_latency = round(time.time() - run_start, 3)

    run_result = {
        "test_case":      case,
        "final_state":    final_state,
        "nodes_visited":  nodes_visited,
        "node_outputs":   node_outputs,
        "node_latencies": node_latencies,
        "total_latency":  total_latency,
        "agent_logs":     log_buffer.getvalue(),
        "scores":         {},
        "overall_score":  0.0,
        "error":          error,
    }

    run_result["scores"]        = _score_run(run_result)
    run_result["overall_score"] = _compute_overall(run_result["scores"])

    return run_result


def _score_run(run_result):
    """
    _score_run
    ----------
    Runs all scorers against one run_result. Scorers return None when they
    do not apply to the given test case — those are excluded from results.

    Args:
        run_result (dict): the RunResult without scores filled in yet

    Returns:
        dict: {scorer_name: ScoreResult}  — only applicable scorers included
    """
    scores = {}
    for name, fn in SCORER_FNS.items():
        result = fn(run_result)
        if result is not None:
            scores[name] = result
    return scores


def _compute_overall(scores):
    """
    _compute_overall
    ----------------
    Averages the scores of all applicable scorers into a single 0.0–1.0 number.
    Returns 1.0 for test cases with no applicable scorers (nothing to fail).

    Args:
        scores (dict): {scorer_name: ScoreResult}

    Returns:
        float: 0.0 to 1.0
    """
    if not scores:
        return 1.0
    total = sum(s["score"] for s in scores.values())
    return round(total / len(scores), 3)
