from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class RolePolicyInferenceAdapter:
    """Clean V1 inference stub for later learned role policies."""

    def __init__(self, model_path: Path | None = None):
        self.model_path = model_path
        self.model = self._load_model(model_path) if model_path else {"kind": "scripted_stub"}

    def predict(self, role: str, frame: dict[str, Any]) -> dict[str, Any]:
        policy = frame.get("policy_output", {})
        return {
            "role": role,
            "adapter": self.model.get("kind", "scripted_stub"),
            "mode": policy.get("mode", "hold"),
            "intent": policy.get("intent", "hold"),
            "confidence": 1.0 if self.model.get("kind") == "scripted_stub" else 0.5,
        }

    @staticmethod
    def _load_model(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"kind": "missing_model_stub", "path": str(path)}
        return json.loads(path.read_text(encoding="utf-8"))
