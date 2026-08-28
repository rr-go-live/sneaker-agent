# 05 — Evaluation Harness

How the system measures itself, what the numbers mean, and what they have already
caught.

---

## Why this exists

An LLM feature without evals is a feature nobody can safely change.

Traditional software has a signal: you edit code, tests fail, you know. Prompt-driven
systems have no such thing by default. Someone rewords a prompt, routing quality drops
8%, and nobody finds out until support tickets accumulate weeks later with no way to
reproduce them. There is no stack trace for "the assistant started ignoring half my
question."

The harness turns behavior into numbers that move. It runs the real pipeline — real
model calls, real database, real catalog — against 15 fixed cases and scores each on
the dimensions that apply to it.

---

## Running it

```bash
python eval_runner.py                # all 15 cases
python eval_runner.py --id TC-003    # one case
python eval_runner.py --verbose      # show agent stdout during runs
```

Or from the browser on the Evals page with an admin session, which streams each case
as it finishes. Admins can also run a free-text one-off scenario, scored only on
dimensions that do not require a fixed expected outcome.

The CLI path needs no server. The graph is built once and reused across all cases —
recompiling per case would add avoidable overhead to a suite that already takes ~160
seconds.

---

## The seven dimensions

| Dimension | Question it answers | Applies when |
| --- | --- | --- |
| Routing accuracy | Did the orchestrator pick the right first agent? | `expected_first_agent` is set |
| Sneaker validity | Is every proposed name a real catalog item? | `expect_proposed_sneakers` is true |
| Expected pick | Did a specific known-correct item actually appear? | `expected_pick_included` is set |
| Constraint fidelity | Does every pick honor brand, silhouette, price, and year? | `expected_constraints` is set |
| Bid fairness | Did the bid agent accept/reject as expected? | `expected_accepted` is set |
| Failure handling | Did a bad input produce a readable message, not a crash? | `is_failure_case` is true |
| Latency | Did the run finish under threshold? | Always |

A scorer returning `None` means it does not apply and is **excluded from that case's
average** rather than counted as a pass. This matters more than it sounds: counting
inapplicable dimensions as passes inflates every score toward 100% and makes the
number useless. A collection-review case has no sneaker picks to validate, so pick
validity is not a thing it passed — it is a thing that was not asked.

### Scoring mechanics

Most dimensions are binary — 1.0 or 0.0. Three award partial credit, and each has a
reason:

**Sneaker validity** scores `valid_picks / total_picks`. Four real picks and one
hallucination is genuinely better than five hallucinations, and a system degrading
from 100% to 80% is a signal you want to see before it reaches 0%.

**Constraint fidelity** scores `compliant_picks / total_picks` for the same reason,
and its `reason` string names each violating pick with the specific field that failed
(`brand=Nike`, `retail=$220`). A failure you can act on beats a failure you have to
reproduce.

**Failure handling** has three tiers: 1.0 for a graceful message, 0.5 when output
exists but is missing the expected text, 0.0 for a crash or empty output. The middle
tier separates "wrong message" from "no message", which are different bugs.

**Latency** is a step function:

| Elapsed | Score |
| --- | --- |
| < 15s | 1.0 |
| 15–30s | 0.5 |
| ≥ 30s | 0.0 |

Case score = mean of applicable scorer scores. A case **passes** when no exception
escaped *and* every applicable scorer's `passed` flag is true. So a case can score 83%
and still pass — partial credit lowers the score without failing the check when the
scorer itself considers the result acceptable.

---

## The 15 cases

### Routing and core flows

| ID | Input | Checks |
| --- | --- | --- |
| TC-001 | "Help me find some fresh kicks to add to my collection" | Routes to `sneaker_agent` despite the word "collection", produces picks |
| TC-002 | "What sneakers do I already have in my collection?" | Routes to `inventory_agent`, produces *no* picks |
| TC-003 | "What do I already own, and what new heat can I cop…" | Compound request — enters at `inventory_agent` *and* produces picks |
| TC-004 | "What are the hottest sneaker styles and trends right now?" | Advice framing still routes to `sneaker_agent` |
| TC-005 | "Is the Jordan 4 Retro Infrared available right now?" | Named-item stock question routes to `logistics_agent` |
| TC-006 | "I want to buy some new heat for my collection" (alice) | Same intent, different user and wardrobe |
| TC-007 | "sneakers" | Single-word input does not crash |

TC-001 and TC-002 are a deliberate pair. Both contain the word "collection" and they
must route differently — one is adding to it, one is reviewing it. Testing them
together is what makes routing quality measurable rather than anecdotal, and it is
what keeps the deterministic pre-check regex honest: a pattern that catches TC-001
would break it.

### Constraint extraction from free text

| ID | Input | Constraints checked |
| --- | --- | --- |
| TC-011 | "the single highest retail value Jordan released after 2022" | brand=Jordan, min_year=2022, plus a specific expected pick |
| TC-012 | "a low top jordan sneaker that I can get with 150 dollars" | brand=Jordan, profile=low, max_price=150 |
| TC-013 | "what is the cheapest New Balance you have" | brand=New Balance, ascending price sort |
| TC-014 | "black Nike low tops under 120 dollars" | brand=Nike, profile=low, max_price=120, plus color |

These four are the end-to-end guard on the whole free-text extraction path. Routing
can be right and every name can be real while the picks quietly ignore what the shopper
asked for — constraint fidelity is the only dimension that catches that.

TC-011 is doing extra work. It is the only case with `expected_pick_included`, naming
one exact catalog item as the correct answer. This is a *superlative* query, where any
in-stock Jordan from 2022 onward would pass validity and constraint checks while still
being the wrong answer. It is also the regression test for sort-before-cap. The
correct answer — Jordan 1 Low SE True Blue, $1,110 retail — ranks **147th out of 311**
qualifying Jordans by popularity. Under the default ranking it sits far outside the
80-row window and never reaches the model at all, so the question is unanswerable no
matter how good the prompt is. A change that reorders sorting and capping fails this
case and nothing else in the suite.

TC-013 tests the ascending sort — and implicitly, that entries with `retail_price: 0`
sort last rather than first. "Cheapest" answered with an unpriced shoe would pass
brand compliance and validity.

TC-014 stacks three hard constraints plus a color preference that has no data behind
it, so it exercises the soft-fallback path alongside three hard filters.

### Bidding

| ID | Bid | Expected |
| --- | --- | --- |
| TC-008 | $50 on a shoe with a $325 lowest ask | Rejected — model judgment |
| TC-009 | $320 on the same shoe | Accepted — model judgment |
| TC-010 | $500 on "Definitely Not A Real Sneaker XYZ" | Rejected — deterministic, no model call |

TC-008 and TC-009 bracket the same sneaker from both sides, which is what makes them
meaningful. A single bid case can be passed by an agent that always rejects. Two cases
in opposite directions cannot.

TC-010 doubles as a failure-handling case, checking the output contains "not a real
catalog item". It confirms the deterministic pre-check fires before the model call —
if it did not, the model would be asked to price a nonexistent shoe.

Bid cases restock their target to quantity 1 before running, so results do not depend
on what earlier manual purchases left in the shared dev database. TC-010's fake name is
deliberately left alone so the "not a real catalog item" path actually fires.

### Failure handling

| ID | Input | Expected |
| --- | --- | --- |
| TC-015 | "find me a jordan under 10 dollars" | Output contains "No in-stock sneakers matched" |
| TC-010 | Bid on a nonexistent sneaker | Output contains "not a real catalog item" |

TC-015 is the honesty test. The catalog holds no Jordan under $10, and the tempting
behaviors — return the cheapest Jordan anyway, or return nothing with no explanation —
are both wrong. The correct answer names the failing constraint. It also verifies the
`no_matches` short-circuit: without it, critique would retry twice and overwrite that
specific message with "Picks approved after review."

---

## Current results

```
15 test cases  |  15/15 passed  |  total time: 161.8s  |  overall score: 93%

  ID        Test Case                               Score    Time  Status
  TC-001    Direct shopping request                 100%   12.4s  PASS
  TC-002    Collection check only — no shopping     100%    3.5s  PASS
  TC-003    Inventory review then shopping           83%   20.4s  PASS
  TC-004    Style advice request                    100%   11.1s  PASS
  TC-005    Stock availability check                100%    1.0s  PASS
  TC-006    Alice shopping request                   83%   15.2s  PASS
  TC-007    Minimal query — no crash                 50%   19.9s  PASS
  TC-008    Lowball bid rejected                    100%    2.5s  PASS
  TC-009    Fair bid accepted                       100%    3.0s  PASS
  TC-010    Bid on unknown sneaker rejected         100%    0.0s  PASS
  TC-011    Highest retail Jordans post-2022        100%   10.9s  PASS
  TC-012    Free-text brand + silhouette + budget    88%   27.9s  PASS
  TC-013    Cheapest New Balance                    100%    8.0s  PASS
  TC-014    Colorway + brand + budget stack          88%   25.0s  PASS
  TC-015    Impossible budget fails honestly        100%    1.3s  PASS

  SCORES BY DIMENSION
  Routing Accuracy      ████████████████████  11/11 cases  100%
  Sneaker Validity      ████████████████████  8/8 cases    100%
  Expected Pick         ████████████████████  1/1 cases    100%
  Constraint Fidelity   ████████████████████  4/4 cases    100%
  Bid Fairness          ████████████████████  3/3 cases    100%
  Failure Handling      ████████████████████  2/2 cases    100%
  Latency               █████████████████░░░  10/15 cases   83%
```

Every quality dimension is at 100%. Every score below 100% on an individual case is
latency dragging that case's average down — TC-007 scores 50% because latency is the
*only* applicable dimension and it ran slow.

Latency is the honest weak point. `sneaker_agent` sends up to 80 catalog rows and
regularly takes 15–30 seconds. The 15-second threshold could have been raised to 30 to
turn 83% into 100% with a one-line edit. It was not, because a threshold moved until
your system passes it measures nothing. Mitigation options are in
[02-ai-ml-design.md](02-ai-ml-design.md#known-limitation--latency).

---

## What the harness has already caught

**TC-003 — the compound-request routing bug.**

The case *"I want to upgrade my sneaker collection. What do I already own, and what
new heat can I cop?"* expects entry at `inventory_agent` and picks produced. It routed
to `sneaker_agent` instead — skipping the collection review entirely — **5 out of 5
runs**.

The 5/5 reproduction rate is what made this actionable. A 1-in-5 failure is temperature
noise you might route around with a retry. A 5-in-5 failure is a deterministic
misclassification with a cause you can find.

Root cause was prompt wording on two counts: the orchestrator prompt called
`sneaker_agent` *"the default for anything sneaker-related"*, and it offered no rule at
all for a message carrying two intents. Shopping language dominated, and the collection
half of the request was silently dropped.

Fixed with a deterministic regex pre-check that routes collection-referencing language
to `inventory_agent` with no model call. `inventory_agent`'s own downstream check hands
off to `sneaker_agent` when it detects shopping intent, so the compound request reaches
both agents in the right order.

Without this test case, the failure mode reaching users would have been "it answered
half my question" — vague, hard to reproduce, and easy to dismiss as a one-off.

---

## Design decisions in the harness itself

**Two execution kinds, one result shape.** Graph cases stream through LangGraph; bid
cases call `evaluate_bid()` directly. Both produce an identical `RunResult`, so the
seven scorers and the report have no idea which path produced what. Adding a third
kind means writing one runner function, not editing seven scorers.

**Per-node latency, not just total.** `node_latencies` measures the gap between
successive stream chunks, which localizes a slowdown to a specific agent instead of
telling you the run was slow. That is the difference between a metric and a
diagnosis.

**Agent stdout is captured, not suppressed.** Redirected into a buffer and stored on
the result, so the report stays clean while the logs remain available. `--verbose`
turns redirection off entirely.

**Exceptions are caught and recorded, never raised.** A crash in case 3 must not
prevent cases 4 through 15 from running. The exception message lands in
`result["error"]`, the case fails, and the suite continues.

**Custom scenarios score only what applies.** The admin free-text runner sets every
expectation field to `None`, so it is scored on latency alone. It is an exploration
tool, and pretending it produces a meaningful quality score would be worse than
scoring nothing.

---

## What is not measured, and what would be added next

Gaps worth naming:

| Missing | Why it matters |
| --- | --- |
| Recommendation *quality* | Validity and compliance are checked; whether the picks are actually good style matches is not. Would need human ratings or an LLM-as-judge rubric. |
| Consistency across runs | Every case runs once. `temperature=0` makes this mostly stable, but variance is unmeasured. Three runs with a variance report would surface flakiness. |
| Token cost per case | Latency is tracked, spend is not. Would catch a prompt change that quietly triples cost. |
| Concurrent load | Every case runs sequentially. Nothing measures behavior under simultaneous requests. |
| Retry-path coverage | No case forces a critique rejection, so the retry loop is exercised only incidentally. |
| Adversarial input | Prompt injection through the free-text box is untested. |

The first three are the ones that would earn their place soonest. Cost tracking in
particular is cheap to add — the token counts are already in the API responses — and
catches a whole class of regression that no current dimension would notice.

---

## Business impact, if this shipped

**This is what makes the feature changeable.** Anyone can edit a prompt and rerun the
suite to see whether they improved things or broke routing. Without it, prompt changes
are unfalsifiable opinions, and the practical consequence is that teams stop touching
prompts that work — which means the system stops improving.

**Regression detection before customers do it for you.** TC-003 was a real bug that
would have shipped. In production it would have surfaced as a slow trickle of
complaints about the assistant ignoring part of a request, with no reproduction path
and no obvious owner. The harness turned it into a named failing case with a root
cause in one debugging session.

**Numbers move procurement and roadmap conversations.** "100% catalog validity across
every case that produces picks" is an answer to *"can we put this in front of
customers?"* that survives scrutiny. "It seems to work well" is not. The same applies
internally when deciding whether an LLM feature is ready to expand.

**Honest metrics are worth more than flattering ones.** The 83% latency score is the
most valuable number in the report, because it points at the one real problem and
quantifies it. A report where everything is green tells you nothing and gets ignored
within a month.

**Dimension-level scoring localizes regressions.** When the overall number drops, the
per-dimension breakdown says whether routing, extraction, validation, or speed moved.
That converts "something got worse" into "constraint fidelity dropped to 76%, look at
the extraction path" — which is the difference between a bug hunt and a fix.
