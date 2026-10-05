"""Bind a passive reader to the exact owned live client, never a rewrite client."""
import json
from pathlib import Path
from . import runtime


def main():
    runtime.monitor()
    games = [row for row in runtime.windows() if row['title'] == 'World of Warcraft']
    if len(games) != 1:
        raise RuntimeError('expected exactly one owned live game window')
    pid = games[0]['pid']
    game = Path(f'/proc/{pid}/cwd').resolve()
    if game != Path.home() / 'Games/_whitemane-60895_':
        raise RuntimeError('live client installation changed')
    with Path(f'/proc/{pid}/mem').open('rb', buffering=0):
        pass  # Check read-only access without reading or saving process bytes.
    row = {'runtime': runtime.owned_process(), 'game_pid': pid,
           'game_start_ticks': runtime.proc_start(pid), 'game_directory': str(game),
           'idle_timeout_seconds': 1800, 'fixed_session_limit': None,
           'raw_capture_saved': False, 'memory_writes': False}
    runtime.write(runtime.ROOT / 'run/bearing_scope.json', row)
    print(json.dumps({'owned_game_pid': pid, 'monitor': 'HDMI-1', 'idle_timeout_seconds': 1800}))


if __name__ == '__main__':
    main()
