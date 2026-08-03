#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "mcp" / "manifest.yaml"
STATE_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Cerebro"
STATE_FILE = STATE_DIR / "mcp-state.json"

GREEN = "\033[92m"
GREY = "\033[90m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def enable_colors() -> bool:
    if not os.isatty(1):
        return False
    if os.name != "nt":
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


COLOR = enable_colors()


def paint(text: str, tone: str) -> str:
    return f"{tone}{text}{RESET}" if COLOR else text


def load_manifest() -> dict[str, Any]:
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Invalid MCP manifest.")
    return data


def default_state() -> dict[str, Any]:
    manifest = load_manifest()
    return {
        "schema": "cerebro-mcp-state/v1",
        "state": manifest["mcp"]["default_state"],
        "source": "default",
        "scope": manifest["state_policy"]["deactivation_scope"],
    }


def load_state() -> dict[str, Any]:
    if not STATE_FILE.is_file():
        return default_state()
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if data.get("state") not in ("active", "inactive"):
            return default_state()
        return data
    except Exception:
        return default_state()


def save_state(state: str) -> dict[str, Any]:
    data = {
        "schema": "cerebro-mcp-state/v1",
        "state": state,
        "source": "user-command",
        "scope": "current-runtime-context",
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


def render(state: dict[str, Any]) -> None:
    active = state["state"] == "active"
    symbol = "●" if active else "○"
    state_text = "ACTIVE" if active else "INACTIVE"
    mode = "Structured control" if active else "Standard chat"
    tone = GREEN if active else GREY
    width = 48

    print()
    print(paint("╭" + "─" * width + "╮", CYAN))
    print(
        paint("│ ", CYAN)
        + paint("MCP · MASTER CONTROL PROGRAM".ljust(width - 2), BOLD)
        + paint(" │", CYAN)
    )
    print(paint("├" + "─" * width + "┤", CYAN))

    rows = [
        ("MCP", state_text),
        ("Level", "1"),
        ("Mode", mode),
        ("Authority", "Control layer"),
    ]
    for label, value in rows:
        left = f"{symbol if label == 'MCP' else ' '} {label}"
        gap = max(1, width - 2 - len(left) - len(value))
        print(
            paint("│ ", CYAN)
            + paint(left, tone if label == "MCP" else "")
            + " " * gap
            + paint(value, tone if label == "MCP" else "")
            + paint(" │", CYAN)
        )

    print(paint("├" + "─" * width + "┤", CYAN))
    result = "MCP ACTIVE" if active else "STANDARD CHAT MODE"
    print(
        paint("│ ", CYAN)
        + paint(("RESULT: " + result).ljust(width - 2), tone)
        + paint(" │", CYAN)
    )
    print(paint("╰" + "─" * width + "╯", CYAN))
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Control MCP state")
    parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=("status", "on", "off", "på", "pa", "av"),
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    if args.action in ("on", "på", "pa"):
        state = save_state("active")
    elif args.action in ("off", "av"):
        state = save_state("inactive")
    else:
        state = load_state()

    if args.json_output:
        print(json.dumps(state, indent=2))
    else:
        render(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
