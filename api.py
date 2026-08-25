"""
api.py
------
FastAPI backend for the Sneaker Agent web application.

Endpoints:
  GET  /api/sneakers              — full catalog with optional filters
  POST /api/agent                 — runs the multi-agent pipeline (SSE stream)
  POST /api/evals/run             — runs the eval harness (SSE stream)
  GET  /api/users                 — list all user profiles
  GET  /api/users/{username}      — get a single user's profile + wardrobe
  POST /api/users/{username}/wardrobe        — add a sneaker to wardrobe
  DELETE /api/users/{username}/wardrobe/{name} — remove a sneaker from wardrobe
  POST /api/inventory/purchase    — buy at listed price; decrements inventory
  POST /api/bid                   — offer a price; an agent judges fairness against
                                     real market data and purchases automatically if accepted

Run with:
  uvicorn api:app --reload
"""

import json
import os
import secrets
import asyncio
import threading
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from data.catalog import SNEAKER_CATALOG
from database import (
    User, WardrobeItem, SneakerInventory,
    get_or_create_user, get_session, get_sneaker_quantity,
    purchase_sneaker, get_out_of_stock_names, init_db, verify_login,
)
from graph import build_graph
from agents.bid_agent import evaluate_bid
from evals.cases import TEST_CASES

init_db()

app = FastAPI(title="Sneaker Agent API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Signs the session cookie used for login. Set SESSION_SECRET in .env so
# sessions survive a server restart; without it, a random key is generated
# for this process only and everyone is logged out on the next restart.
_session_secret = os.environ.get("SESSION_SECRET")
if not _session_secret:
    _session_secret = secrets.token_hex(32)
    print(
        "WARNING: SESSION_SECRET not set in .env — using a random key for "
        "this process only. Logins will not survive a server restart. "
        "Set SESSION_SECRET=<random value> in .env to fix this."
    )

app.add_middleware(SessionMiddleware, secret_key=_session_secret, same_site="lax")

# Human-readable labels for each LangGraph node
NODE_LABELS = {
    "orchestrator":    "Orchestrator",
    "sneaker_agent":   "Sneaker Advisor",
    "inventory_agent": "Inventory Agent",
    "critique_agent":  "Critique Agent",
    "logistics_agent": "Logistics Agent",
}


# ─────────────────────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────────────────────

class AgentInput(BaseModel):
    """
    AgentInput
    ----------
    Request body for POST /api/agent.

    Fields:
        input    (str):         natural language query from the UI
        wardrobe (list[str]):   sneakers the user already owns; skips inventory lookup
        brands   (list[str]):   brand chips selected in the form; hard-filtered
                                by sneaker_agent instead of left to the LLM
        colors   (list[str]):   colorway chips selected in the form
    """
    input:    str
    wardrobe: list[str]       = []
    brands:   list[str]       = []
    colors:   list[str]       = []


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/sneakers")
def get_sneakers(
    q:         Optional[str]   = Query(None, description="Search term"),
    brand:     Optional[str]   = Query(None, description="Brand name filter"),
    profile:   Optional[str]   = Query(None, description="high / mid / low"),
    max_price: Optional[float] = Query(None, description="Maximum retail price"),
    in_stock:  Optional[bool]  = Query(None, description="True = in stock only"),
):
    """
    get_sneakers
    ------------
    Returns catalog entries as a list. All filter params are optional and combinable.

    Args:
        q         (str):   partial match against name, brand, or colorway
        brand     (str):   exact brand match (case-insensitive)
        profile   (str):   high / mid / low
        max_price (float): maximum retail_price
        in_stock  (bool):  filter to in-stock items only

    Returns:
        list[dict]: matching sneakers with 'name' field prepended
    """
    results = []

    for name, details in SNEAKER_CATALOG.items():
        brand_value = details.get("brand", "")
        colorway_value = details.get("colorway", "")

        if q:
            target = (name + brand_value + colorway_value).lower()
            if q.lower() not in target:
                continue
        if brand and brand_value.lower() != brand.lower():
            continue
        if profile and details.get("profile", "") != profile.lower():
            continue
        if max_price is not None and details.get("retail_price", 0) > max_price:
            continue
        if in_stock is not None and details.get("in_stock", False) != in_stock:
            continue

        results.append({"name": name, **details})

    return results


@app.post("/api/agent")
async def run_agent(body: AgentInput):
    """
    run_agent
    ---------
    Runs the full LangGraph multi-agent pipeline and streams each node's
    completion as an SSE event the moment it finishes.

    Uses a background thread for the synchronous LangGraph calls and an
    asyncio.Queue bridged via loop.call_soon_threadsafe so the async generator
    yields each step in real time rather than all at once after the graph ends.

    SSE event shapes:
      {"type": "agent_step", "node": "...", "label": "...", "summary": "...", "reasoning": "...", "next": "..."|null}
      {"type": "result",     "sneakers": [...], "output": "..."}
      {"type": "error",      "message": "..."}
      [DONE]

    Args:
        body (AgentInput): user input, optional brand/color filters, optional wardrobe

    Returns:
        StreamingResponse: SSE stream
    """
    async def generate():
        initial_state = {
            "input":            body.input,
            "user_name":        "web_user",
            "requested_brands": body.brands,
            "requested_colors": body.colors,
        }

        if body.wardrobe:
            initial_state["sneaker_collection"] = body.wardrobe

        loop       = asyncio.get_running_loop()
        queue      = asyncio.Queue()
        final_state: dict = {}

        def run_graph():
            """
            run_graph
            ---------
            Runs graph.stream() in a background thread. Each completed node is
            posted to the asyncio queue immediately so the async generator can
            yield it without waiting for the full graph to finish.
            """
            try:
                graph = build_graph()
                for chunk in graph.stream(initial_state, stream_mode="updates"):
                    for node_name, updates in chunk.items():
                        loop.call_soon_threadsafe(
                            queue.put_nowait, ("step", node_name, updates)
                        )
            except Exception as exc:
                loop.call_soon_threadsafe(
                    queue.put_nowait, ("error", str(exc), {})
                )
            finally:
                loop.call_soon_threadsafe(
                    queue.put_nowait, ("done", None, None)
                )

        thread = threading.Thread(target=run_graph, daemon=True)
        thread.start()

        while True:
            kind, node_name, updates = await queue.get()

            if kind == "error":
                yield f"data: {json.dumps({'type': 'error', 'message': node_name})}\n\n"
                yield "data: [DONE]\n\n"
                return

            if kind == "done":
                break

            # Stream this node's completion to the client immediately
            final_state.update(updates)

            next_node  = updates.get("next")
            next_clean = next_node if next_node in NODE_LABELS else None

            event = {
                "type":      "agent_step",
                "node":      node_name,
                "label":     NODE_LABELS.get(node_name, node_name),
                "summary":   _node_summary(node_name, updates),
                "reasoning": updates.get("reasoning", ""),
                "next":      next_clean,
            }
            yield f"data: {json.dumps(event)}\n\n"

        thread.join(timeout=2)

        # Build the final result event with live inventory quantities
        proposed = final_state.get("proposed_sneakers", [])
        sneakers = []
        for s in proposed:
            if s not in SNEAKER_CATALOG:
                continue
            details  = dict(SNEAKER_CATALOG[s])
            quantity = get_sneaker_quantity(s)
            details["quantity"] = quantity
            details["in_stock"] = quantity > 0
            sneakers.append({"name": s, **details})

        result = {
            "type":     "result",
            "sneakers": sneakers,
            "output":   final_state.get("output", ""),
        }
        yield f"data: {json.dumps(result)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "http://localhost:5173",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Eval routes
# ─────────────────────────────────────────────────────────────────────────────

class EvalRunRequest(BaseModel):
    """
    EvalRunRequest
    --------------
    Optional request body for POST /api/evals/run.

    Fields:
        case_id      (str|None): if given, run only the test case with this
                                 ID. Ignored when custom_input is set.
        custom_input (str|None): a free-text prompt to run through the full
                                 pipeline as a one-off scenario instead of
                                 the fixed TEST_CASES suite.
    """
    case_id:      Optional[str] = None
    custom_input: Optional[str] = None


@app.post("/api/evals/run")
async def run_evals(body: EvalRunRequest, request: Request):
    """
    run_evals
    ---------
    Runs the eval harness against the agent graph and streams each completed
    test case as an SSE event the moment it finishes.

    Admin-only — the eval dashboard exposes internal routing/scoring detail
    that isn't meant for regular shopping accounts. Enforced here (not just
    hidden in the UI) so a direct API call is rejected the same way.

    Uses a background thread (synchronous runner.py) bridged to the async
    FastAPI generator via asyncio.Queue, matching the pattern used by /api/agent.

    SSE event shapes:
      {"type": "eval_case",    "id": "...", "name": "...", "passed": bool,
       "overall_score": float, "total_latency": float,
       "nodes_visited": [...], "node_latencies": {...},
       "scores": {...}, "output": "...", "error": "..."|null}
      {"type": "eval_summary", "total": int, "passed": int,
       "avg_score": float,     "total_time": float,
       "dimension_scores": {dim: {"avg": float, "pass_count": int, "total": int}}}
      [DONE]

    Args:
        body    (EvalRunRequest): optional case_id filter or custom_input
        request (Request):        used to read the session for the admin check

    Returns:
        StreamingResponse: SSE stream

    Raises:
        HTTPException: 403 if the session isn't an admin
    """
    if not request.session.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    async def generate():
        if body.custom_input:
            cases = [{
                "id":                       "CUSTOM",
                "name":                     "Custom scenario",
                "description":              "Ad-hoc admin scenario — no fixed expected outcome, "
                                             "scored only on dimensions that don't require one (e.g. latency).",
                "input":                    body.custom_input,
                "user_name":                "admin",
                "expected_first_agent":     None,
                "expect_proposed_sneakers": False,
                "is_failure_case":          False,
                "expected_output_contains": None,
            }]
        elif body.case_id:
            cases = [c for c in TEST_CASES if c["id"] == body.case_id]
            if not cases:
                event = {"type": "error", "message": f"No test case with id '{body.case_id}'"}
                yield f"data: {json.dumps(event)}\n\n"
                yield "data: [DONE]\n\n"
                return
        else:
            cases = list(TEST_CASES)

        loop    = asyncio.get_running_loop()
        queue   = asyncio.Queue()
        all_results: list = []

        def run_evals_thread():
            """
            run_evals_thread
            ----------------
            Runs each test case sequentially in a background thread, posting
            each completed RunResult to the asyncio queue for real-time streaming.
            """
            try:
                from graph import build_graph as _build
                app_graph = _build()
                from evals.runner import _run_one_case
                for case in cases:
                    result = _run_one_case(app_graph, case, verbose=False)
                    loop.call_soon_threadsafe(queue.put_nowait, ("case", result))
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, ("error", str(exc)))
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, ("done", None))

        thread = threading.Thread(target=run_evals_thread, daemon=True)
        thread.start()

        while True:
            kind, payload = await queue.get()

            if kind == "error":
                yield f"data: {json.dumps({'type': 'error', 'message': payload})}\n\n"
                yield "data: [DONE]\n\n"
                return

            if kind == "done":
                break

            result = payload
            all_results.append(result)

            case    = result["test_case"]
            scores  = result["scores"]
            passed  = not result.get("error") and all(s["passed"] for s in scores.values())

            event = {
                "type":          "eval_case",
                "id":            case["id"],
                "name":          case["name"],
                "description":   case["description"],
                "input":         case["input"],
                "user_name":     case["user_name"],
                "passed":        passed,
                "overall_score": result["overall_score"],
                "total_latency": result["total_latency"],
                "nodes_visited": result["nodes_visited"],
                "node_latencies": result["node_latencies"],
                "scores":        scores,
                "output":        result["final_state"].get("output", ""),
                "error":         result.get("error"),
            }
            yield f"data: {json.dumps(event)}\n\n"

        thread.join(timeout=2)

        # Build dimension aggregate summary
        dimension_data: dict = {}
        for r in all_results:
            for dim, score_result in r["scores"].items():
                if dim not in dimension_data:
                    dimension_data[dim] = []
                dimension_data[dim].append(score_result["score"])

        dimension_scores = {}
        for dim, scores_list in dimension_data.items():
            avg        = sum(scores_list) / len(scores_list)
            pass_count = sum(1 for s in scores_list if s >= 1.0)
            dimension_scores[dim] = {
                "avg":        round(avg, 3),
                "pass_count": pass_count,
                "total":      len(scores_list),
            }

        total     = len(all_results)
        passed_ct = sum(
            1 for r in all_results
            if not r.get("error") and all(s["passed"] for s in r["scores"].values())
        )
        avg_score  = sum(r["overall_score"] for r in all_results) / total if total else 0
        total_time = sum(r["total_latency"] for r in all_results)

        summary = {
            "type":             "eval_summary",
            "total":            total,
            "passed":           passed_ct,
            "avg_score":        round(avg_score, 3),
            "total_time":       round(total_time, 2),
            "dimension_scores": dimension_scores,
        }
        yield f"data: {json.dumps(summary)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "http://localhost:5173",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _node_summary(node_name: str, updates: dict) -> str:
    """
    _node_summary
    -------------
    Produces a one-line human-readable summary of what a node did.
    Used as the 'summary' field in agent_step SSE events.

    Args:
        node_name (str):  LangGraph node name
        updates   (dict): state updates returned by that node

    Returns:
        str: short summary string
    """
    if node_name == "orchestrator":
        next_node = updates.get("next", "")
        return f"Routing to {NODE_LABELS.get(next_node, next_node)}"

    if node_name == "inventory_agent":
        collection = updates.get("sneaker_collection") or []
        count      = len(collection)
        return f"Reviewed {count} item{'s' if count != 1 else ''} in your collection"

    if node_name == "sneaker_agent":
        picks = updates.get("proposed_sneakers") or []
        if picks:
            preview = ", ".join(" ".join(p.split()[:3]) for p in picks[:2])
            suffix  = "..." if len(picks) > 2 else ""
            return f"Selected: {preview}{suffix}"
        return "No picks matched catalog"

    if node_name == "critique_agent":
        feedback = updates.get("critique_feedback")
        attempts = updates.get("critique_attempts", 1)
        if feedback:
            short = feedback[:40] + "…" if len(feedback) > 40 else feedback
            return f"Rejected (attempt {attempts}): {short}"
        return f"Approved after {attempts} review{'s' if attempts != 1 else ''}"

    if node_name == "logistics_agent":
        return "Availability and pricing confirmed"

    return "Processing"


# ─────────────────────────────────────────────────────────────────────────────
# Auth routes
# ─────────────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    """
    LoginRequest
    ------------
    Request body for POST /api/auth/login.

    Fields:
        username (str): account username
        password (str): plaintext password, checked against the stored hash
    """
    username: str
    password: str


@app.post("/api/auth/login")
def login(body: LoginRequest, request: Request):
    """
    login
    -----
    Verifies username/password and, on success, stores the identity in a
    signed session cookie so subsequent requests know who's logged in.

    Returns 401 for any failure (unknown user, no password set, wrong
    password) without distinguishing which — avoids confirming whether a
    given username exists.
    """
    user = verify_login(body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    request.session["username"] = user["username"]
    request.session["is_admin"] = user["is_admin"]
    return user


@app.post("/api/auth/logout")
def logout(request: Request):
    """
    logout
    ------
    Clears the session cookie.
    """
    request.session.clear()
    return {"ok": True}


@app.get("/api/auth/me")
def me(request: Request):
    """
    me
    --
    Returns the currently logged-in user from the session, or 401 if no
    one is logged in. Used by the frontend on page load to restore auth
    state after a refresh.
    """
    username = request.session.get("username")
    if not username:
        raise HTTPException(status_code=401, detail="Not logged in")
    return {"username": username, "is_admin": request.session.get("is_admin", False)}


# ─────────────────────────────────────────────────────────────────────────────
# User profile routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/users")
def list_users():
    """
    list_users
    ----------
    Returns all user profiles (id, username, wardrobe item count).
    """
    with get_session() as db:
        users = db.query(User).order_by(User.username).all()
        return [
            {
                "username":      u.username,
                "wardrobe_count": len(u.wardrobe),
            }
            for u in users
        ]


@app.get("/api/users/{username}")
def get_user(username: str):
    """
    get_user
    --------
    Returns a single user's profile including their full wardrobe list.
    """
    with get_session() as db:
        user = db.query(User).filter_by(username=username).first()
        if user is None:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        return {
            "username": user.username,
            "wardrobe": [item.sneaker_name for item in user.wardrobe],
        }


class AddWardrobeItem(BaseModel):
    sneaker_name: str


@app.post("/api/users/{username}/wardrobe")
def add_to_wardrobe(username: str, body: AddWardrobeItem):
    """
    add_to_wardrobe
    ---------------
    Adds a sneaker to the user's wardrobe. Creates the user if not found.
    Silently ignores duplicates (UniqueConstraint handles it).
    """
    with get_session() as db:
        user = get_or_create_user(db, username)
        existing = (
            db.query(WardrobeItem)
            .filter_by(user_id=user.id, sneaker_name=body.sneaker_name)
            .first()
        )
        if existing is None:
            db.add(WardrobeItem(user_id=user.id, sneaker_name=body.sneaker_name))
        wardrobe = [
            item.sneaker_name
            for item in db.query(WardrobeItem).filter_by(user_id=user.id).all()
        ]
        return {"username": username, "wardrobe": wardrobe}


@app.delete("/api/users/{username}/wardrobe/{sneaker_name}")
def remove_from_wardrobe(username: str, sneaker_name: str):
    """
    remove_from_wardrobe
    --------------------
    Removes one sneaker from the user's wardrobe by name.
    """
    with get_session() as db:
        user = db.query(User).filter_by(username=username).first()
        if user is None:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        item = (
            db.query(WardrobeItem)
            .filter_by(user_id=user.id, sneaker_name=sneaker_name)
            .first()
        )
        if item:
            db.delete(item)
        wardrobe = [
            i.sneaker_name
            for i in db.query(WardrobeItem).filter_by(user_id=user.id).all()
        ]
        return {"username": username, "wardrobe": wardrobe}


# ─────────────────────────────────────────────────────────────────────────────
# Inventory routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/inventory/{sneaker_name}")
def get_inventory(sneaker_name: str):
    """
    get_inventory
    -------------
    Returns the current stock quantity for a single sneaker.
    """
    quantity = get_sneaker_quantity(sneaker_name)
    return {
        "sneaker_name": sneaker_name,
        "quantity":     quantity,
        "in_stock":     quantity > 0,
    }


def _purchase_and_add_to_wardrobe(sneaker_name: str, username: Optional[str]):
    """
    _purchase_and_add_to_wardrobe
    ------------------------------
    Decrements live inventory by 1 and, if a username is given, adds the
    sneaker to that user's wardrobe (skipping if already owned). Shared by
    the flat-price purchase route and an accepted bid, so both paths
    remove a sneaker from inventory the same way.

    Args:
        sneaker_name (str):      exact catalog name
        username     (str|None): if provided, sneaker is added to their wardrobe

    Returns:
        int | None: remaining quantity if the purchase succeeded, or None
                     if the sneaker was already out of stock
    """
    success = purchase_sneaker(sneaker_name)
    if not success:
        return None

    if username:
        with get_session() as db:
            user = get_or_create_user(db, username)
            already_owned = (
                db.query(WardrobeItem)
                .filter_by(user_id=user.id, sneaker_name=sneaker_name)
                .first()
            )
            if not already_owned:
                db.add(WardrobeItem(user_id=user.id, sneaker_name=sneaker_name))

    return get_sneaker_quantity(sneaker_name)


class PurchaseRequest(BaseModel):
    """
    PurchaseRequest
    ---------------
    Fields:
        sneaker_name (str):       exact catalog name to purchase
        username     (str|None):  if provided, sneaker is added to their wardrobe
    """
    sneaker_name: str
    username:     Optional[str] = None


@app.post("/api/inventory/purchase")
def purchase(body: PurchaseRequest, request: Request):
    """
    purchase
    --------
    Decrements inventory by 1. Requires a logged-in session — enforced here,
    not just hidden in the UI, so a direct API call is rejected the same way.
    Returns 409 if out of stock. If username is provided, also adds the
    sneaker to the user's wardrobe.
    """
    if not request.session.get("username"):
        raise HTTPException(status_code=401, detail="Log in to purchase")

    remaining = _purchase_and_add_to_wardrobe(body.sneaker_name, body.username)
    if remaining is None:
        raise HTTPException(status_code=409, detail="Out of stock")

    return {
        "success":      True,
        "sneaker_name": body.sneaker_name,
        "quantity":     remaining,
    }


class BidRequest(BaseModel):
    """
    BidRequest
    ----------
    Request body for POST /api/bid.

    Fields:
        sneaker_name (str):       exact catalog name being bid on
        bid_amount   (float):     the offered dollar amount
        username     (str|None):  if provided and the bid is accepted, the
                                  sneaker is added to their wardrobe
    """
    sneaker_name: str
    bid_amount:   float
    username:     Optional[str] = None


@app.post("/api/bid")
def place_bid(body: BidRequest, request: Request):
    """
    place_bid
    ---------
    Evaluates a bid against the sneaker's real market data (bid_agent.py).
    If accepted, immediately purchases it — same mechanics as the flat-price
    Purchase button (decrements inventory, adds to wardrobe if a username
    was given).

    Requires a logged-in session — enforced here (checked before the LLM
    call, not after) so an unauthenticated request never spends one.

    Returns 409 if the bid is accepted but the sneaker sold out between
    evaluation and purchase (a live race, not an evaluation failure).
    """
    if not request.session.get("username"):
        raise HTTPException(status_code=401, detail="Log in to place a bid")

    out_of_stock = get_out_of_stock_names()
    result = evaluate_bid(body.sneaker_name, body.bid_amount, SNEAKER_CATALOG, out_of_stock)

    if not result["accepted"]:
        return {
            "accepted":  False,
            "reasoning": result["reasoning"],
            "purchased": False,
            "quantity":  get_sneaker_quantity(body.sneaker_name),
        }

    remaining = _purchase_and_add_to_wardrobe(body.sneaker_name, body.username)
    if remaining is None:
        raise HTTPException(
            status_code=409,
            detail="Bid was accepted but the sneaker sold out just now",
        )

    return {
        "accepted":  True,
        "reasoning": result["reasoning"],
        "purchased": True,
        "quantity":  remaining,
    }
