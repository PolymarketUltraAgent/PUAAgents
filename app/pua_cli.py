#!/usr/bin/env python3
"""JSON entrypoint for the PUA agent pipeline, spawned by the Telegram bot.

Run from the PUAAgents repo root so `orchestrator` is importable:

    python3 app/pua_cli.py --tags politics,economics --top-n 5

Prints a single JSON object on the last line of stdout:

    {"ok": true, "decisions": [ ...TradeDecision dicts... ]}
    {"ok": false, "error": "..."}
"""
import argparse
import json
import os
import sys
from dataclasses import asdict, is_dataclass

# This file lives in <repo>/app/, but `orchestrator` is a package at the repo
# root. Running `python3 app/pua_cli.py` only puts `app/` on sys.path, so add
# the repo root explicitly to make the import work regardless of cwd.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the PUA agent pipeline")
    parser.add_argument("--tags", default="", help="comma-separated Polymarket tag slugs")
    parser.add_argument("--top-n", type=int, default=5, help="max markets to analyze")
    args = parser.parse_args()

    tags = [t.strip() for t in args.tags.split(",") if t.strip()] or None

    try:
        from orchestrator import run

        decisions = run(tags=tags, top_n=args.top_n)
        payload = [asdict(d) if is_dataclass(d) else d for d in decisions]
        # Marker line keeps the JSON parseable even if the pipeline logged above.
        print(json.dumps({"ok": True, "decisions": payload}))
        return 0
    except Exception as exc:  # noqa: BLE001 - surface any pipeline failure to the bot
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
