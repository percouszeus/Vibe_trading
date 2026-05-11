"""
orchestrator/__main__.py
────────────────────────
Allows running the orchestrator as a module:
    python -m orchestrator --health
    python -m orchestrator --phase premarket
    python -m orchestrator --daemon
"""

from orchestrator.daily_cycle import main

if __name__ == "__main__":
    main()
