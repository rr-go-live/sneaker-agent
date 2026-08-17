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
  PUT  /api/users/{username}      — update budget
  POST /api/users/{username}/wardrobe        — add a sneaker to wardrobe
  DELETE /api/users/{username}/wardrobe/{name} — remove a sneaker from wardrobe

Run with:
  uvicorn api:app --reload
"""

import json
import asyncio
import threading
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from data.catalog import SNEAKER_CATALOG
from database import (
    User, WardrobeItem, SneakerInventory,
    get_or_create_user, get_session, get_sneaker_quantity,
    purchase_sneaker, init_db,
)
from graph import build_graph
from evals.cases import TEST_CASES

init_db()

app = FastAPI(title="Sneaker Agent API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Human-readable labels for each LangGraph node
NODE_LABELS = {
    "orchestrator":    "Orchestrator",
    "financial_agent": "Financial Agent",
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
        budget   (float|None):  pre-set budget from the form; skips financial_agent lookup
        wardrobe (list[str]):   sneakers the user already owns; skips inventory lookup
    """
    input:    str
    budget:   Optional[float] = None
    wardrobe: list[str]       = []


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
        body (AgentInput): user input, optional budget, optional wardrobe

    Returns:
        StreamingResponse: SSE stream
    """
    async def generate():
        initial_state = {"input": body.input, "user_name": "web_user"}

        if body.budget is not None and body.budget > 0:
            initial_state["budget"] = body.budget
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
        case_id (str|None): if given, run only the test case with this ID.
                            If omitted, all cases are run.
    """
    case_id: Optional[str] = None


@app.post("/api/evals/run")
async def run_evals(body: EvalRunRequest):
    """
    run_evals
    ---------
    Runs the eval harness against the agent graph and streams each completed
    test case as an SSE event the moment it finishes.

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
        body (EvalRunRequest): optional case_id filter

    Returns:
        StreamingResponse: SSE stream
    """
    async def generate():
        if body.case_id:
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

    if node_name == "financial_agent":
        budget = updates.get("budget")
        return f"Budget confirmed: ${budget:.2f}" if budget else updates.get("output", "")

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
# User profile routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/users")
def list_users():
    """
    list_users
    ----------
    Returns all user profiles (id, username, budget, wardrobe item count).
    """
    with get_session() as db:
        users = db.query(User).order_by(User.username).all()
        return [
            {
                "username":      u.username,
                "budget":        u.budget,
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
            "budget":   user.budget,
            "wardrobe": [item.sneaker_name for item in user.wardrobe],
        }


class UpdateBudget(BaseModel):
    budget: float


@app.put("/api/users/{username}")
def update_user(username: str, body: UpdateBudget):
    """
    update_user
    -----------
    Creates or updates a user's budget.
    """
    with get_session() as db:
        user = get_or_create_user(db, username)
        user.budget = body.budget
        return {"username": user.username, "budget": user.budget}


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
def purchase(body: PurchaseRequest):
    """
    purchase
    --------
    Decrements inventory by 1. Returns 409 if out of stock. If username is
    provided, also adds the sneaker to the user's wardrobe.
    """
    success = purchase_sneaker(body.sneaker_name)
    if not success:
        raise HTTPException(status_code=409, detail="Out of stock")

    if body.username:
        with get_session() as db:
            user = get_or_create_user(db, body.username)
            already_owned = (
                db.query(WardrobeItem)
                .filter_by(user_id=user.id, sneaker_name=body.sneaker_name)
                .first()
            )
            if not already_owned:
                db.add(WardrobeItem(user_id=user.id, sneaker_name=body.sneaker_name))

    remaining = get_sneaker_quantity(body.sneaker_name)
    return {
        "success":      True,
        "sneaker_name": body.sneaker_name,
        "quantity":     remaining,
    }
