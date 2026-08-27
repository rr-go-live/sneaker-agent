"""
runner.py
---------
Runs test cases and collects results. Two kinds of test cases exist
(see evals/cases.py):

  kind="graph" (default) — runs the full LangGraph agent graph. For each
    case it:
      1. Calls app.stream() with stream_mode="updates" — this yields one
         chunk per agent node as it completes, so we can capture per-node
         outputs and timing
      2. Merges all node outputs into a final_state dict

  kind="bid" — calls agents.bid_agent.evaluate_bid() directly, since
    bidding is a standalone flow outside the graph (one already-known
    sneaker + a dollar amount, not a routing decision). final_state is
    synthesized from the {"accepted", "reasoning"} dict evaluate_bid returns.

Both kinds converge on the same RunResult shape, so scoring (scorers.py)
and reporting (report.py) never need to know which kind produced a result.

Agent print statements are suppressed during graph runs so they don't
pollute the eval output. Pass verbose=True to run_all_cases() to see them.
"""

import io
import time
import contextlib

from graph import build_graph
from data.catalog import SNEAKER_CATALOG
from database import get_out_of_stock_names, restock_sneaker
from agents.bid_agent import evaluate_bid
from evals.cases import TEST_CASES
from evals import scorers as sc


# Maps scorer names to the functions in scorers.py
SCORER_FNS = {
    "routing":           sc.score_routing,
    "sneaker_validity":  sc.score_sneaker_validity,
    "expected_pick":     sc.score_expected_pick,
    "constraints":       sc.score_constraint_compliance,
    "bid_outcome":       sc.score_bid_outcome,
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
    Dispatches a test case to the runner matching its 'kind' field
    ("graph", the default, or "bid") and scores the result the same way
    regardless of which path produced it.

    Args:
        app     (CompiledGraph): the compiled LangGraph app (unused for bid cases)
        case    (dict):          a test case from cases.py
        verbose (bool):          if True, agent stdout is shown (graph cases only)

    Returns:
        dict: RunResult with keys:
          test_case, final_state, nodes_visited, node_outputs,
          node_latencies, total_latency, agent_logs, scores,
          overall_score, error
    """
    if case.get("kind") == "bid":
        return _run_bid_case(case)
    return _run_graph_case(app, case, verbose=verbose)


def _run_bid_case(case):
    """
    _run_bid_case
    -------------
    Runs a bid-kind test case by calling bid_agent.evaluate_bid() directly —
    bidding targets one already-known sneaker and isn't a graph routing
    decision, so there's no LangGraph pipeline to stream through.

    Args:
        case (dict): a test case from cases.py with kind="bid"

    Returns:
        dict: RunResult, same shape _run_graph_case produces, so scorers
              and report.py need no branching. nodes_visited is the
              single-element ["bid_agent"] for display consistency.
    """
    run_start = time.time()
    error     = None
    result    = {"accepted": False, "reasoning": ""}

    # Bid tests exercise fairness/validation logic, not real inventory —
    # guarantee a known-good stock level for a real catalog item so the
    # result doesn't depend on what prior manual purchases left behind in
    # the shared dev database. A test double / nonexistent name (like
    # TC-010's) is left alone so the "not a real catalog item" path fires.
    if case["sneaker_name"] in SNEAKER_CATALOG:
        restock_sneaker(case["sneaker_name"], quantity=1)

    try:
        result = evaluate_bid(
            case["sneaker_name"],
            case["bid_amount"],
            SNEAKER_CATALOG,
            get_out_of_stock_names(),
        )
    except Exception as exc:
        error = str(exc)

    total_latency = round(time.time() - run_start, 3)

    final_state = {
        "accepted":  result["accepted"],
        "output":    result["reasoning"],
        "reasoning": result["reasoning"],
    }

    run_result = {
        "test_case":      case,
        "final_state":    final_state,
        "nodes_visited":  ["bid_agent"],
        "node_outputs":   {"bid_agent": final_state},
        "node_latencies": {"bid_agent": total_latency},
        "total_latency":  total_latency,
        "agent_logs":     "",
        "scores":         {},
        "overall_score":  0.0,
        "error":          error,
    }

    run_result["scores"]        = _score_run(run_result)
    run_result["overall_score"] = _compute_overall(run_result["scores"])

    return run_result


def _run_graph_case(app, case, verbose=False):
    """
    _run_graph_case
    ----------------
    Runs one graph-kind test case through the LangGraph agent graph using
    streaming mode.

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
