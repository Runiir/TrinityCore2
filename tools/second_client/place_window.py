"""Place an exact game-window PID on the second physical monitor and verify it."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time


def second_monitor() -> dict:
    result = subprocess.check_output(["xrandr", "--listmonitors"], text=True)
    monitors = []
    for line in result.splitlines()[1:]:
        match = re.search(r"(\d+)/\d+x(\d+)/\d+([+-]\d+)([+-]\d+)\s+(\S+)", line)
        if match:
            width, height, x, y, name = match.groups()
            monitors.append({"name": name, "x": int(x), "y": int(y),
                             "width": int(width), "height": int(height)})
    if len(monitors) < 2:
        raise RuntimeError("second monitor is unavailable; refusing a primary-monitor game launch")
    return monitors[1]


def place(pid: int, timeout: float = 30) -> dict:
    from Xlib import X, display
    from Xlib.protocol import event

    monitor = second_monitor()
    screen = display.Display(os.environ.get("DISPLAY", ":0"))
    root = screen.screen().root
    clients_atom = screen.intern_atom("_NET_CLIENT_LIST")
    pid_atom = screen.intern_atom("_NET_WM_PID")
    if not 0 < timeout <= 120:raise ValueError('invalid owned-window startup timeout')
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        clients = root.get_full_property(clients_atom, X.AnyPropertyType)
        for xid in clients.value if clients is not None else []:
            window = screen.create_resource_object("window", int(xid))
            owner = window.get_full_property(pid_atom, X.AnyPropertyType)
            if owner is None or not len(owner.value) or int(owner.value[0]) != pid:
                continue
            geometry = window.get_geometry()
            x = monitor["x"] + max(0, (monitor["width"] - geometry.width) // 2)
            y = monitor["y"] + max(0, (monitor["height"] - geometry.height) // 2)
            message = event.ClientMessage(window=window.id,
                client_type=screen.intern_atom("_NET_MOVERESIZE_WINDOW"),
                data=(32, [(1 << 8) | (1 << 9) | (2 << 12), x, y, 0, 0]))
            root.send_event(message, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
            screen.flush()
            for _ in range(20):
                time.sleep(0.1)
                location = root.translate_coords(window, 0, 0)
                cx, cy = location.x + geometry.width / 2, location.y + geometry.height / 2
                if (monitor["x"] <= cx < monitor["x"] + monitor["width"]
                        and monitor["y"] <= cy < monitor["y"] + monitor["height"]):
                    result = {"monitor": monitor, "pid": pid, "window_id": int(xid),
                              "window": {"x": location.x, "y": location.y,
                                         "width": geometry.width, "height": geometry.height},
                              "second_monitor_verified": True}
                    screen.close()
                    return result
        time.sleep(0.2)
    screen.close()
    raise RuntimeError("could not verify the owned game window on the second monitor")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument('--timeout', type=float, default=30)
    args = parser.parse_args()
    result = place(args.pid,args.timeout)
    if args.receipt:
        args.receipt.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
