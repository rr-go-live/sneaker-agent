# 00 — System Overview

## What it is

Sneaker Agent turns a sentence into a shortlist. A shopper types something like
*"a low top jordan under $150 released after 2022"* and gets back a set of real,
in-stock sneakers that satisfy every part of that sentence, each with retail price,
current resale value, and a live stock count.

Behind that single input sit five cooperating agents, a 1,668-item catalog with real
StockX market data, a SQLite store of users and inventory, and an eval harness that
scores the whole pipeline on seven dimensions every time it runs.

## The problem it solves

Sneaker retail has a search problem that ordinary filters do not fix.

A shopper's real intent is compound. *"Low top Jordan under $150 released after 2022"*
is four constraints stacked in one breath — silhouette, brand, price ceiling, release
recency. Conventional e-commerce handles this with a sidebar of checkboxes, which
works only if the shopper knows which boxes exist, in what order, and is willing to
click through five of them. Most people give up or settle.

A naive LLM chatbot handles it in one message but introduces a worse failure: it
invents products. Ask a general-purpose model for a Jordan under $150 and it will
happily name a colorway that has never existed, quote a price it made up, and present
both with total confidence. In retail that is not a quirky output — it is a customer
who arrives at checkout for a shoe you do not sell.

This system takes the natural-language front door and removes the hallucination risk
behind it. The model never picks from the catalog freely. It picks from a pool that
Python has already filtered down to items that satisfy every stated constraint, and
anything it names that was not in that pool is discarded before the shopper sees it.

## Who it serves

| Actor | What they do | Where they enter |
| --- | --- | --- |
| Shopper | Describes what they want, browses the catalog, buys or bids | React SPA at `localhost:5173` |
| Admin | Runs the eval suite, runs ad-hoc scenarios against the pipeline | Same SPA, Evals page (admin session required) |
| Developer | Runs the eval harness and CLI tests without a browser | `python eval_runner.py`, `python cli_test.py` |

## What the system does

1. **Routes** — decides which specialist handles a request (recommend, review the
   collection, check stock on a named pair).
2. **Resolves constraints** — pulls brand, colorway, silhouette, price ceiling,
   release-year floor, ordering preference, and pick count out of either UI filter
   chips or raw prose.
3. **Filters deterministically** — narrows 1,668 sneakers to a candidate pool in
   plain Python before any model sees it.
4. **Selects for style** — asks the LLM to choose from that pool, which is the one
   part of the job that genuinely needs judgment.
5. **Critiques** — a second agent checks the picks and can send them back for one
   retry with specific feedback.
6. **Reports availability** — live stock quantity, retail, and market value per pick.
7. **Evaluates bids** — a standalone agent judges whether an offer on one specific
   pair is fair against real market data, and buys it on the spot if it is.
8. **Scores itself** — 15 test cases across 7 dimensions, runnable from the CLI or
   the browser.

## Scope boundaries

Deliberately out of scope, and why:

| Not included | Reasoning |
| --- | --- |
| Account balances or budgets | An earlier version tracked a per-user balance. It was removed because it made most of the catalog unreachable in demos without adding anything to the recommendation problem. A price ceiling the shopper states themselves is honored as a filter — that is a constraint, not a balance. |
| Payment processing | Purchase decrements inventory and adds to a wardrobe. Money movement is a separate problem with its own compliance surface. |
| Real-time market data | Market prices are a point-in-time snapshot in `sneakerdata.json`. Live pricing would be a scheduled sync job, not a request-time API call. |
| Multi-size inventory | Every sneaker is one SKU with one quantity. Size-level stock multiplies the schema without changing the agent logic. |
| Product images at request time | Images are backfilled offline via `backfill_images.py`. Fetching them per request would put a third-party API in the critical path of every page load. |

## Technology choices and the reasoning

| Layer | Choice | Why this one |
| --- | --- | --- |
| Agent framework | LangGraph 1.1 | Agents are nodes in a state graph with conditional edges. The retry loop between critique and selection is a cycle, which a linear chain framework cannot express without hand-rolled control flow. |
| LLM | Gemini 2.5 Flash, `temperature=0` | Cheapest tier that clears the quality bar for these tasks. Every prompt is short, structured, and asks for a constrained answer — not the kind of work that needs a frontier model. Temperature 0 keeps routing decisions repeatable, which the eval harness depends on. |
| API | FastAPI + Uvicorn | Async request handling with native streaming responses. The agent pipeline takes 10–30 seconds, so streaming partial progress is not a nice-to-have. |
| Persistence | SQLAlchemy 2.0 + SQLite | Real ORM models against a zero-setup file database. The models port to Postgres by changing one URL. |
| Frontend | React 18 + Vite + React Router | Standard SPA stack. Vite's dev server proxies to the API without a build step between edits. |
| Auth | Signed session cookies + PBKDF2-HMAC-SHA256 | No external identity provider needed for a local build, and password storage follows current OWASP iteration guidance rather than something invented for a demo. |

## Business impact, if this shipped

The system is not in production. What follows is what each design choice would be
worth if it were.

**Hallucination containment is the whole value proposition.** A retail assistant that
names a product you do not sell generates a support ticket, an abandoned cart, and a
customer who trusts the next recommendation less. The guardrail here — validate the
model's answer against the exact pool it was shown, discard anything else — makes that
class of failure structurally impossible rather than statistically rare. Eval results
show 100% sneaker validity across every case that produces picks. That number is not
a prompt-engineering win; it holds because the code, not the prompt, enforces it.

**Constraint fidelity protects conversion.** Every returned pick satisfies every
stated constraint, because violations are filtered out before selection. A shopper who
says "under $150" and receives a $220 shoe does not adjust their expectations — they
leave. Deterministic filtering means the price ceiling is honored by construction.

**Honest empty results beat helpful substitutions.** When nothing matches, the system
says which combination failed ("No in-stock sneakers matched brand(s) Jordan, low-top,
under $80") instead of quietly widening the search. In retail, a silent substitution
reads as a bait-and-switch. Naming the blocking constraint also converts a dead end
into a next step — the shopper knows which knob to turn.

**The eval harness is the operational story.** Most LLM features ship with no
regression signal at all: a prompt change goes live and nobody knows it broke routing
until customers complain. This system scores routing accuracy, pick validity,
constraint compliance, bid fairness, failure handling, and latency on every run. That
turns "the assistant feels worse today" into a number that moved. It is what makes an
LLM feature maintainable by a team rather than by whoever wrote the prompt.

**Cost stays predictable because most decisions never reach a model.** Three to four
LLM calls per shopping request, each with a bounded prompt, and several decision points
handled in Python for free. Cost scales with traffic in a line, not a curve.

## Non-obvious design decisions worth knowing about

These come up again in later docs, but they are the ideas that shape everything else:

- **The candidate pool is the security boundary.** Not the prompt. The model can only
  return names that were in the list it was handed, and its answer is intersected with
  that list afterward.
- **Deterministic checks run before LLM checks, always.** Count and brand compliance
  are facts. Style fit and value are judgments. Sending a fact to a model wastes money
  and introduces a failure mode that did not need to exist.
- **The router has a deterministic escape hatch.** One class of request — "what do I
  own, and what should I buy next" — misrouted 5 out of 5 times through the LLM. A
  regex pre-check now handles it before any model call. Documented in
  [02-ai-ml-design.md](02-ai-ml-design.md#the-routing-bug-and-what-it-taught).
- **Sort before you cap.** The pool is capped at 80 rows before the model sees it. For
  a superlative query ("most expensive Jordan"), the correct answer is defined by
  price and would sit far outside a popularity-ranked window. Ordering has to happen
  first or the question is unanswerable regardless of prompt quality.
