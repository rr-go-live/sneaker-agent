"""
eval_runner.py
--------------
CLI entry point for the sneaker agent eval harness.

This script runs the agent system against a battery of test cases and prints a
scored report. It is the main way to verify that the multi-agent pipeline is
working correctly end-to-end.

HOW THE EVAL WORKS
------------------
For each test case the runner:
  1. Sends the input through the full LangGraph agent graph
  2. Captures which nodes ran, in what order, and how long each took
  3. Runs up to 6 scorers against the result:

     Routing Accuracy    — did the orchestrator pick the right first agent?
     Budget Accuracy     — did financial_agent find the correct budget?
     Sneaker Validity    — are all proposed sneakers real catalog items (no hallucination)?
     Budget Compliance   — does the total retail price stay within the user's budget?
     Failure Handling    — does the system fail gracefully when something goes wrong?
     Latency             — did the full run finish within the acceptable time window?

  4. Averages all applicable scores into a per-case overall score
  5. Aggregates scores per dimension across all cases for the final report

USAGE
-----
  python eval_runner.py                 # run all 8 test cases
  python eval_runner.py --id TC-001     # run one specific test case
  python eval_runner.py --verbose       # show agent logs during runs
"""

import sys
import argparse

from evals.cases import TEST_CASES
from evals.runner import run_all_cases
from evals.report import print_report


def parse_args():
    """
    parse_args
    ----------
    Parses CLI arguments.

    Supported flags:
      --id <TC-XXX>   run only the test case with this ID
      --verbose       show agent print statements during runs

    Returns:
        argparse.Namespace
    """
    parser = argparse.ArgumentParser(
        description="Run the sneaker agent eval harness and print a scored report."
    )
    parser.add_argument(
        "--id",
        type=str,
        default=None,
        help="Run only the test case with this ID (e.g. --id TC-001)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Show agent logs (print statements) while test cases run",
    )
    return parser.parse_args()


def main():
    """
    main
    ----
    Filters test cases if --id is given, runs them, and prints the report.

    Exits with code 1 if --id is given but not found in TEST_CASES.

    Returns:
        None
    """
    args = parse_args()

    if args.id:
        cases = [c for c in TEST_CASES if c["id"] == args.id]
        if not cases:
            print(f"No test case found with id '{args.id}'")
            available = [c["id"] for c in TEST_CASES]
            print(f"Available IDs: {available}")
            sys.exit(1)
    else:
        cases = TEST_CASES

    print(f"Running {len(cases)} test case(s)...")
    print("(Agent logs suppressed — use --verbose to show them)\n" if not args.verbose else "")

    results = run_all_cases(cases, verbose=args.verbose)
    print_report(results)


if __name__ == "__main__":
    main()
