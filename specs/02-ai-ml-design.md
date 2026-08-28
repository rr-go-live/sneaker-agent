# 02 — AI/ML Design

How the model is used, where it is deliberately not used, and what keeps it honest.

---

## The core idea

The model is a stylist, not a database.

Every question with one correct answer — does this sneaker exist, is it in stock, is
it under $150, is it a low top, did it release after 2022, are there exactly five
picks — is answered in Python. Every question that genuinely needs judgment — which of
these forty valid options fits what this person described, is this bid fair, does this
request imply shopping — goes to the model.

That split is the single most important design decision in the system, and everything
below is a consequence of it.

---

## Pattern 1 — Filter-then-select (grounding)

The system never asks the model to search 1,668 sneakers. It hands the model a
pre-filtered pool of at most 80 and asks it to choose.

```
1,668 catalog items
      ↓  deterministic filters (stock, brand, silhouette, price, year)
    ~40 valid candidates
      ↓  sort + cap
     ≤80 rows into the prompt
      ↓  LLM selects for style
      5 picks
      ↓  intersect with the pool it was shown
      5 validated picks
```

Two properties fall out of this that no prompt can give you:

**Constraint compliance is structural.** The pool physically cannot contain a $220
shoe when the ceiling is $150. There is no wording the model could produce that
violates the ceiling, because no violating item was ever in front of it.

**Hallucination is filtered, not prevented.** The model can still invent a name — they
do. `extract_proposed_names` intersects the answer against the candidate list, so an
invented name matches nothing and is dropped. The measured result is 100% catalog
validity across every eval case that produces picks.

### Why colorway is the exception

Colorway is a *soft* preference, not a hard filter, and the reason is data quality
rather than design preference. Colorway strings are missing across large parts of the
catalog. A hard filter on "grey" would return an empty pool for most color requests
and produce a false "nothing matched" — the shoes exist, the metadata does not.

So the filter falls back to the full pool when nothing matches, returns a
`color_matched = False` flag, and the prompt is told directly: *"no candidate has a
confirmed grey colorway in the data below, so pick the closest style match and say so
in your reasoning."* The shopper gets an answer plus an honest caveat instead of a
wrong dead end.

The general rule: **hard-filter attributes that are complete and exact; soft-prefer
attributes that are sparse.** Brand, silhouette, retail price, and release date are
present on every entry. Colorway is not.

---

## Pattern 2 — Actor–critic with bounded retries

`sneaker_agent` proposes. `critique_agent` reviews. On rejection, the specific reason
is injected into `sneaker_agent`'s next prompt and it tries again.

```
sneaker_agent → critique_agent → approved → logistics_agent
                      ↓ rejected (with reason)
                sneaker_agent (retry, feedback in prompt)
```

Three rules make this safe:

**The loop is bounded.** `MAX_CRITIQUE_ATTEMPTS = 2`, then force-approve. An unbounded
critic loop is an unbounded bill and a hung request. Two cycles catch the common
mistakes; beyond that the marginal improvement does not justify two more model calls
and ten more seconds.

**Deterministic checks run first.** Pick count and brand compliance are checked in
Python before any critique model call. A count mismatch is a fact — sending it to a
model to "evaluate" wastes a call and adds a way to get it wrong.

**Unsatisfiable requests skip the loop entirely.** When `no_matches` is set, critique
passes straight through with the explanation intact. Retrying an impossible request
just burns two cycles and then overwrites a specific, useful message ("nothing matched
under $80") with a generic one ("picks approved").

### Rubric scoping

The critic evaluates two rubrics, and one of them is conditionally removed.

| Rubric | When it applies |
| --- | --- |
| Value — at least one pick appreciates above retail | Always |
| Diversity — picks are not all one brand | Only when no brand was requested |

Five Jordans in response to "show me Jordans" is a correct answer, not a diversity
failure. Leaving the rubric in would make the critic reject correct output, trigger a
retry that cannot succeed, and burn the retry budget on a non-problem. **A rubric that
can contradict the user's own request must be scoped to the cases where it makes
sense.**

---

## Pattern 3 — LLM as intent router, with a deterministic override

`orchestrator` reads the request and picks one of three specialists. This is
zero-shot intent classification: no training data, no fine-tuning, just a prompt
describing each agent and asking which one fits.

It works well for single-intent requests. Routing accuracy across the eval suite is
100%.

### The routing bug, and what it taught

A compound request — *"what do I already own, and what new heat can I cop to complete
the rotation?"* — routed to `sneaker_agent` **5 out of 5 times**, skipping
`inventory_agent` entirely, even though the message plainly asks about the existing
collection.

Two causes, both prompt-level:

1. The prompt described `sneaker_agent` as *"the default for anything sneaker-related"*,
   which biased the model toward it whenever any shopping language appeared.
2. The prompt gave no rule at all for a message carrying two intents.

The reproduction rate matters. 5/5 is not temperature noise to retry around — it is a
deterministic misclassification, and no amount of rerunning fixes it.

**The fix was to stop asking.** A regex pre-check (`_mentions_existing_collection`)
now routes collection-referencing language straight to `inventory_agent` with no model
call. `inventory_agent`'s own downstream check hands off to `sneaker_agent` when it
detects shopping intent, so the compound request still reaches both agents — in the
right order.

The regex is deliberately narrower than "mentions the word collection". *"Add to my
collection"* and *"new heat for my collection"* both use that word and are pure
shopping requests. Every alternative in the pattern requires a checking or viewing
verb alongside the noun.

A false positive costs one extra collection summary. A false negative costs the user
half of what they asked for. The asymmetry justifies erring toward the pre-check.

---

## Pattern 4 — The two-part response contract

Several agents ask for exactly this shape:

```
REASONING: <2-3 sentences explaining the decision>
ANSWER: <the machine-readable value>
```

`reasoning.py::split_reasoning_answer` splits them. The parser is deliberately
forgiving — labels match in any case, and a missing label degrades instead of raising.
If `ANSWER:` is absent the whole response is treated as the answer; if `REASONING:` is
absent the text before `ANSWER:` is used as reasoning.

This pattern buys three things at once:

**Explainability at zero extra cost.** The reasoning streams to the UI log panel so
the shopper can follow why each agent decided what it did. Asking a second time
("explain yourself") would double the call count for the same information.

**A parse target that survives chattiness.** Models like to preamble. Splitting on a
labeled marker means the conversational lead-in lands in the reasoning half instead of
corrupting the value the code needs.

**Free chain-of-thought.** Writing the reasoning first measurably improves the answer
that follows. Here the reasoning is a product feature, so the quality gain costs
nothing extra.

Downstream parsing stays defensive regardless. Brand-name matching is done by
substring intersection against the candidate pool, and approve/reject is checked with
`.upper().startswith("APPROVED")` — no strict format dependency anywhere.

---

## Pattern 5 — Stating applied constraints as facts

Prompt wording follows one rule that is easy to miss: **tell the model what is already
true, never ask it to enforce what the code has already enforced.**

Bad:
```
Only pick sneakers under $150.
```

What the prompt actually says:
```
Already filtered for you: all options are low-top silhouettes; all options
retail at $150 or less; options are ordered by retail price, highest first.
```

The pool cannot violate the ceiling. Asking the model to enforce it invites
second-guessing — a model told to check something will sometimes decide an item fails,
drop it, and return four picks when five were requested. Stating the constraint as
settled removes that failure mode.

Same logic applies to the brand instruction, which flips between two forms:

| Condition | Prompt text |
| --- | --- |
| Brand requested | "Every option below already matches the requested brand(s): Jordan." |
| No brand requested | "No specific brand was requested — favor variety across brands." |

Before free-text brand extraction existed, a brand named in prose was dropped and the
model received the *second* line — actively steering it away from the brand the
shopper had just named. Contradictory instructions inside one prompt are among the
most common causes of "the model ignored me."

---

## Model selection and cost

| Setting | Value | Reasoning |
| --- | --- | --- |
| Model | `gemini-2.5-flash` | Cheapest tier that clears the bar for these tasks. Every prompt is short, structured, and asks for a constrained choice from a supplied list — not open-ended reasoning. |
| Temperature | `0` | Routing must be repeatable or the eval harness measures noise instead of behavior. Style selection loses a little variety and gains reproducibility, which is the right trade for a system you score. |
| Retries | Handled at the agent layer | The critic loop is the retry mechanism. No SDK-level retry stacking on top of it. |

### Call and token budget per request

| Flow | LLM calls | Rough input tokens |
| --- | --- | --- |
| Shopping (no retry) | 3 — orchestrator, sneaker, critique | ~3,500 |
| Shopping (one retry) | 5 | ~6,500 |
| Collection review | 2 — summary, shopping-intent check | ~400 |
| Compound request | 4 — pre-check is free | ~4,000 |
| Stock check | 1 — orchestrator only | ~200 |
| Bid (valid) | 1 | ~250 |
| Bid (invalid) | 0 | 0 |
| Catalog browse | 0 | 0 |

The 80-row candidate block dominates everything — roughly 2,500 of the ~3,500 tokens
in a shopping request. `MAX_CATALOG_SIZE` is the single biggest cost and latency lever
in the system.

Multiply the token counts above by the current Flash-tier rate to get per-request cost;
check the live pricing page rather than trusting a number written into a doc, since
those move. The shape that matters is: cost is bounded per request and scales linearly
with traffic, because the prompt size is capped by construction rather than by how
large the catalog grows.

### Where money is deliberately not spent

| Decision | Handled by | Calls saved |
| --- | --- | --- |
| Does this sneaker exist? | Dict lookup | 1 per bid on a bad name |
| Is it in stock? | DB query | 1 per bid on a sold-out pair |
| Is the bid a positive number? | Comparison | 1 per malformed bid |
| Are there exactly N picks? | `len()` | 1 critique cycle |
| Are all picks the right brand? | Set membership | 1 critique cycle |
| Is this a collection question? | Regex | 1 per compound request |
| Can this request be satisfied at all? | Empty-pool check | 2 retry cycles |
| Is the user logged in? | Session check before the call | 1 per unauthenticated bid |

That last one is a small detail with a real edge: the auth check in `place_bid` runs
*before* `evaluate_bid`, so an unauthenticated request never spends a model call.
Putting an auth check after an expensive operation is a free denial-of-wallet vector.

---

## Known limitation — latency

This is the weakest measured dimension and the number has not been massaged.

`sneaker_agent` sends up to 80 catalog rows to the model and regularly takes 15–30
seconds. Against a 15-second pass threshold, latency scores 83% across the suite while
every other dimension scores 100%.

The threshold was deliberately left at 15 seconds rather than raised to 30 to make the
dashboard look better. Raising a threshold until your system passes it converts a
measurement into decoration.

Options if this needed fixing, roughly in order of what they cost:

| Approach | Effect | Trade-off |
| --- | --- | --- |
| Cut `MAX_CATALOG_SIZE` to ~30 | Large — the pool is most of the prompt | Less variety for the model to choose from |
| Stream the selection response | Perceived, not actual | More client complexity |
| Cache routing decisions for repeated inputs | Removes one call on repeats | Needs a cache layer |
| Run critique concurrently with logistics | Overlaps two steps | Critique can reject, so logistics may run for nothing |
| Skip critique when the pool is small | Removes a call | Loses the value/diversity check |

The honest framing: 10–30 seconds is acceptable for a considered purchase decision and
unacceptable for search-as-you-type. The system is built for the former, and the
catalog browse path — which needs to be instant — has no model calls in it at all.

---

## Business impact, if this shipped

**Guardrails are the difference between a demo and a product.** A recommendation
engine that occasionally invents products cannot go in front of customers at any
scale, because the failure is silent and confident. Making validity a code property
rather than a prompt property is what makes the feature deployable. The eval number
(100% validity) is evidence, not marketing.

**The deterministic/LLM split is what keeps unit economics sane.** Roughly half the
decisions in this system never reach a model. At demo scale that saves pennies. At a
million requests it is the difference between a line item and a problem, and it also
removes half the latency and half the failure surface.

**Explainability changes shopper behavior.** Every agent explains its reasoning in
plain English, streamed live. In retail, a recommendation you can see the logic behind
converts better than one that appears from nowhere — and when the system says "no
confirmed grey colorway in the data, so here's the closest style match", it manages
expectations instead of quietly disappointing.

**The routing bug is the maintainability story.** It was found by a test case, root-
caused to specific prompt wording, and fixed with code rather than more wording. Most
teams shipping LLM features have no mechanism that would have surfaced it at all — it
would have shown up as a slow trickle of "the assistant ignored half my question"
complaints with no way to reproduce. An eval suite turns that into a failing test with
a name.

**Cost scales with traffic, not with catalog size.** The prompt is capped at 80 rows
whether the catalog holds 1,668 sneakers or 100,000. Growth in inventory costs
database time, not token spend — which is exactly the property you want when the
catalog is the thing that grows.
