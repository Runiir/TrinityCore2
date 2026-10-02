"""Bounded Laya decisions over screenshots, addon telemetry and visible TCP objects.

Laya is text-only. Telescope headings come from the owned session's ordinary
visible-object packets. A teacher can annotate a screenshot for mouse looting.
"""
import argparse
import json
import math
import time
import urllib.request

from . import lab_runtime as lab,owned_input
from .observation.telemetry import decode_image

MODEL = "convaiinnovations/laya-typed-decisions"
REVISION = "c5d78730f3493e4fe16d61507ef4b78eef7318cf"
ENDPOINT = "http://127.0.0.1:8000/v1/systemone"
GUIDE = "Recover one archaeology fragment. Follow next_instruction. Survey after each walk. Turn toward the telescope heading before walking. Red: walk farther. Yellow: medium walk. Green: small walk. Loot a revealed find. Observe only if unsafe or casting."
DESCRIPTIONS = {"survey": "Cast Survey to reveal an instrument or find.",
    "forward_short": "Walk forward a small distance toward the instrument direction.",
    "forward_long": "Walk forward farther toward the instrument direction.",
    "turn_left": "Turn left toward the survey instrument direction.",
    "turn_right": "Turn right toward the survey instrument direction.",
    "loot": "Right click the visible archaeology find.",
    "observe": "Wait and inspect the screen without moving."}


def candidates(visual, previous):
    if visual.get("casting") or visual.get("uncertain"): return ["observe"]
    if "fragment_pixel" in visual: return ["loot", "observe"]
    turn = visual.get("turn")
    if turn in {"left", "right"}: return ["turn_" + turn, "observe"]
    if visual.get("aligned") and visual.get("tool_color") in {"green", "yellow", "red"}:
        return ["forward_short", "forward_long", "observe"]
    last_survey = next((r for r in reversed(previous) if r["executed"] == "survey"), None)
    moved = any(r["executed"].startswith("forward_") for r in previous[previous.index(last_survey)+1:]) if last_survey else True
    if not moved: return ["observe"]
    return ["survey", "observe"]


def choose(state, options):
    if options == ["observe"]:
        return {"source": "controller_safety_guard"}, {"answers": {"action": {
            "choice": "observe", "confidence": None}}, "source": "controller_safety_guard"}, "observe"
    payload = {"model": MODEL, "state": state, "questions": {"action": {
        "type": "choice", "instructions": GUIDE, "criteria": {key: DESCRIPTIONS[key] for key in options}}}}
    # A fixed loopback endpoint cannot redirect input/state to another service.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs): return None
    opener = urllib.request.build_opener(NoRedirect)
    request = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with opener.open(request, timeout=15) as response: result = json.load(response)
    if result.get("model") != MODEL or result.get("revision") != REVISION: raise ValueError("unexpected decision model identity")
    answer = result.get("answers", {}).get("action", {})
    if answer.get("type") != "choice" or answer.get("choice") not in options: raise ValueError("invalid action choice")
    if any(v.get("truncated_fields") for v in result.get("token_budget", {}).values()): raise ValueError("truncated decision input")
    return payload, result, answer["choice"]


def automatic_visual(tcp, previous):
    if tcp["finds"]: return {"find_visible": True, "next_instruction": "A find is visible. Locate it on the screenshot for a right click."}
    last_survey = next((r for r in reversed(previous) if r["executed"] == "survey" and r.get("tcp", {}).get("session") == tcp["session"]), None)
    moved = last_survey and any(r["executed"].startswith("forward_") for r in previous[previous.index(last_survey)+1:])
    tool = tcp["tool"]
    if moved or not last_survey or not tool or tool["seen_at"] < last_survey.get("started_at", last_survey["time"]):
        return {"next_instruction": "Cast Survey now to obtain a fresh instrument direction."}
    error = tool["turn_error_radians"]
    if abs(error) > .10:
        direction = "left" if error > 0 else "right"
        return {"tool_color": tool["color"], "turn": direction, "turn_error_radians": error,
                "next_instruction": "Turn " + direction + " toward the telescope heading."}
    return {"tool_color": tool["color"], "aligned": True,
            "next_instruction": "Walk forward " + ("a small distance." if tool["color"] == "green" else "farther toward the telescope heading.")}


def step(visual=None, observer=None):
    from PIL import Image
    from tools.second_client import ctl
    if not lab.owned_process("client") or not lab.owned_process("modern_world"):
        raise RuntimeError("owned client/world endpoint is absent")
    monitor = json.loads((lab.ROOT / "evidence/client_monitor.json").read_text())
    if not monitor["second_monitor_verified"] or monitor["pid"] != lab.owned_process("client")["pid"]:
        raise RuntimeError("current client monitor is unverified")
    path = lab.ROOT / "evidence/laya_archaeology_episode.json"
    episode = json.loads(path.read_text()) if path.exists() else {"schema": "client442_laya_archaeology_trial_v1", "steps": [], "completed": False, "vision_source": "teacher_annotations_of_screenshots", "weights_fine_tuned": False}
    previous = episode["steps"]
    episode["observation_sources"] = ["addon_rendered_pixels", "owned_session_visible_object_tcp_packets", "teacher_loot_pixel_annotations"]
    if len(previous) >= 120 or episode["completed"]: raise RuntimeError("episode is closed or action budget is exhausted")
    if len(previous) >= 4 and all(r["executed"] == "observe" for r in previous[-4:]): raise RuntimeError("no-progress watchdog stopped the episode")
    ctl._launcher_env = lab.client_environment
    index = len(previous)
    before = lab.ROOT / f"evidence/laya_arch_{index:02d}_before.png"
    after = lab.ROOT / f"evidence/laya_arch_{index:02d}_after.png"
    ctl.shot(str(before))
    with Image.open(before) as screenshot: observation = decode_image(screenshot, x=15, y=15, cell_size=3.75)
    if not observation["in_world"] or observation["dead"] or observation["in_combat"] or observation["on_taxi"]:
        raise RuntimeError("character is unavailable for archaeology control")
    from .observation.archaeology import Observer
    observer = observer or Observer()
    tcp = observer.poll(observation["facing_radians"])
    visual = visual if visual is not None else automatic_visual(tcp, previous)
    if visual.get("find_visible") and "fragment_pixel" not in visual:
        print(json.dumps({"status": "find_visible", "tcp": tcp, "screenshot": str(before)}, indent=2))
        return "find_visible"
    # A new native session requires a fresh Survey, even if the preceding login
    # surveyed at the same location. Never reuse another session's instrument.
    scoped = [r for r in previous if r.get("tcp", {}).get("session") == tcp["session"]]
    options = candidates(visual, scoped)
    state = {"task": "archaeology", "addon": {key: observation[key] for key in ["position", "facing_radians", "speed", "health_percent"]},
        "screenshot_observation": visual, "telescope": {k: tcp["tool"][k] for k in ["color", "heading_radians", "turn_error_radians"]} if tcp["tool"] else None,
        "last_actions": [r["executed"] for r in previous[-3:]]}
    payload, response, action = choose(state, options)
    inputs = owned_input.Inputs()
    started_at = time.time()
    hold = None
    if action == "survey": inputs.key("2")
    elif action.startswith("forward_"):
        short, long = {"red": (2, 6), "yellow": (1, 3), "green": (.5, 1)}[visual["tool_color"]]
        hold = short if action == "forward_short" else long
        inputs.key("w", hold=hold)
    elif action.startswith("turn_"):
        hold = min(.55, max(.025, abs(visual.get("turn_error_radians", .5)) / math.pi))
        inputs.key("a" if action == "turn_left" else "d", hold=hold)
    elif action == "loot":
        x, y = visual["fragment_pixel"]
        if not (0 <= x < 1280 and 80 <= y < 630): raise ValueError("find coordinate outside game world")
        inputs.click(x, y, button=3)
    time.sleep(2 if action in {"survey", "loot"} else .5)
    ctl.shot(str(after))
    with Image.open(after) as screenshot: outcome = decode_image(screenshot, x=15, y=15, cell_size=3.75)
    previous.append({"time": time.time(), "started_at": started_at, "observation": observation, "visual": visual, "tcp": tcp, "hold_seconds": hold, "request": payload,
        "response": response, "executed": action, "outcome": outcome,
        "screenshots": [{"file": p.name, "sha256": lab.sha256(p)} for p in [before, after]]})
    if action == "loot":
        from .observation.archaeology import collected
        confirmation = collected(tcp["session"], started_at)
        if confirmation:
            episode.update(completed=True, completion=confirmation)
    lab.private_write(path, json.dumps(episode, indent=2) + "\n")
    print(json.dumps({"step": index, "action": action, "confidence": response["answers"]["action"]["confidence"], "screenshot": str(after)}, indent=2))
    return action


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--visual", help="Optional JSON screenshot annotation, including fragment_pixel")
    parser.add_argument("--steps", type=int, default=1)
    args = parser.parse_args()
    if not 1 <= args.steps <= 120: parser.error("steps must be between 1 and 120")
    from .observation.archaeology import Observer
    observer = Observer()
    for _ in range(args.steps):
        if step(json.loads(args.visual) if args.visual else None, observer) == "find_visible": break


if __name__ == "__main__": main()
