"""
orchestrator/audit.py
──────────────────────
StateAuditor provides high-fidelity logic tracking to identify silent failures,
mismatched inputs/outputs, and data drops across execution phases.
All traces are written to a separate `.audit` file to avoid terminal clutter.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

AUDIT_DIR = Path.home() / ".trading_platform" / "audit_logs"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

class StateAuditor:
    def __init__(self):
        self._today = datetime.now().strftime("%Y-%m-%d")
        self._audit_file = AUDIT_DIR / f"state_{self._today}.audit"

    def log_step(self, phase: str, logic_node: str, context: Dict[str, Any]) -> None:
        """
        Logs an intermediate state trace.
        """
        entry = {
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "phase": phase,
            "logic_node": logic_node,
            "context": context
        }
        with open(self._audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def snapshot(self, phase: str, tag: str, state: Dict[str, Any]) -> None:
        """
        Captures a structural snapshot before or after a major phase.
        """
        self.log_step(phase, f"SNAPSHOT_{tag.upper()}", state)

auditor = StateAuditor()
