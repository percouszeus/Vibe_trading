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

class StateAuditor:
    def _get_audit_file(self) -> Path:
        today = datetime.now().strftime("%Y-%m-%d")
        file_path = AUDIT_DIR / f"state_{today}.audit"
        if not AUDIT_DIR.exists():
            AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        return file_path

    def log_step(self, phase: str, logic_node: str, context: Dict[str, Any]) -> None:
        """
        Logs an intermediate state trace.
        """
        try:
            entry = {
                "timestamp": datetime.now().isoformat(timespec="milliseconds"),
                "phase": phase,
                "logic_node": logic_node,
                "context": context
            }
            audit_file = self._get_audit_file()
            with open(audit_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception:
            pass  # Silent failure is preferred for an audit logger over crashing the system

    def snapshot(self, phase: str, tag: str, state: Dict[str, Any]) -> None:
        """
        Captures a structural snapshot before or after a major phase.
        """
        self.log_step(phase, f"SNAPSHOT_{tag.upper()}", state)

auditor = StateAuditor()
