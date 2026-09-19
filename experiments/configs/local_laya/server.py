"""Pinned local Laya adapter. Reject truncated questions or evidence."""
from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
import os
import threading
import time

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import laya
from fastapi import FastAPI, HTTPException
from huggingface_hub import snapshot_download
from laya.common import build_sequence, render_options, serialize_state
import uvicorn

MODEL = "convaiinnovations/laya-typed-decisions"
REVISION = "c5d78730f3493e4fe16d61507ef4b78eef7318cf"
agent = None
device = "cuda"
inference_lock = threading.Lock()


def token_budget(runtime, state, questions):
    receipts = {}
    for qid, definition in questions.items():
        q = runtime._to_internal(definition)
        tok = runtime.tok
        mask = tok.mask_token
        encode = lambda text: tok(text, add_special_tokens=False)["input_ids"]
        head = encode(f'{q["t"]} question: {q["ins"]}'.replace(mask, " "))
        options = [[tok.mask_token_id] + encode(" " + text.replace(mask, " "))
                   for text in render_options(q)]
        retained_options = [row[:49] for row in options]
        head_limit = runtime.cfg.get("head_max_len", 192)
        option_budget = head_limit - sum(map(len, retained_options))
        if option_budget < 16:
            per_option = max(4, (head_limit - 16) // max(1, len(options)))
            retained_options = [row[:per_option] for row in retained_options]
            option_budget = head_limit - sum(map(len, retained_options))
        retained_head = min(len(head), max(8, option_budget))
        state_tokens = len(encode(serialize_state(state).replace(mask, " ")))
        max_len = runtime.cfg.get("max_len", 512)
        state_room = max(0, max_len - retained_head - sum(map(len, retained_options)) - 4)
        sequence, markers = build_sequence(tok, state, q, max_len, head_limit)
        truncated = []
        if retained_head < len(head):
            truncated.append("instructions")
        if list(map(len, options)) != list(map(len, retained_options)):
            truncated.append("criteria")
        if state_tokens > state_room:
            truncated.append("state")
        if len(markers) != len(options):
            truncated.append("option_markers")
        receipts[qid] = {"input_tokens": len(sequence), "max_tokens": max_len,
                         "state_tokens": state_tokens, "state_budget": state_room,
                         "instruction_tokens": len(head),
                         "instruction_budget": max(8, option_budget),
                         "truncated_fields": truncated}
    return receipts


@asynccontextmanager
async def lifespan(app):
    global agent
    snapshot = snapshot_download("convaiinnovations/laya", revision=REVISION,
                                 allow_patterns=["typed-decisions/*"])
    agent = laya.load(snapshot, subfolder="typed-decisions", device=device)
    yield


app = FastAPI(title="Trinity local Laya diagnostics", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ready" if agent is not None else "loading", "model": MODEL,
            "revision": REVISION, "package_version": laya.__version__,
            "device": str(agent.device) if agent is not None else device,
            "dtype": str(agent.dtype) if agent is not None else None,
            "max_tokens_per_question": agent.cfg.get("max_len") if agent else None,
            "head_max_tokens": agent.cfg.get("head_max_len") if agent else None,
            "truncation_policy": "reject", "action_authority": False}


@app.post("/v1/systemone")
def system_one(payload: dict):
    if payload.get("model", MODEL) != MODEL:
        raise HTTPException(422, "requested model does not match local Laya")
    questions = payload.get("questions")
    state = payload.get("state")
    if not isinstance(state, (dict, list, str)) or not isinstance(questions, dict) or not questions:
        raise HTTPException(422, "state and nonempty questions are required")
    if len(questions) > 16:
        raise HTTPException(422, "at most 16 questions per request")
    try:
        budget = token_budget(agent, state, questions)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(422, f"invalid typed question: {exc}") from exc
    if any(row["truncated_fields"] for row in budget.values()):
        raise HTTPException(422, {"error": "context_budget_exceeded", "token_budget": budget})
    started = time.perf_counter()
    with inference_lock:
        result = agent.predict(state, questions)
    result.update(model=MODEL, revision=REVISION, device=str(agent.device),
                  elapsed_sec=round(time.perf_counter() - started, 6),
                  token_budget=budget, action_authority=False)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    args = parser.parse_args()
    device = args.device
    uvicorn.run(app, host=args.host, port=args.port)
