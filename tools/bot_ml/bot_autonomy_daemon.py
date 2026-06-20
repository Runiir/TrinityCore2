from __future__ import annotations

from .orchestrator_daemon import *  # noqa: F401,F403
from .orchestrator_daemon import main


if __name__ == "__main__":
    raise SystemExit(main())
