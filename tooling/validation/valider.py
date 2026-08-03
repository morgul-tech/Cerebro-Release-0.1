#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]

SOURCE_REPO = "morgul-tech/Cerebro-Source-1.0"
RELEASE_REPO = "morgul-tech/Cerebro-Release-0.1"
BRANCH = "main"
MCP_STATE_FILE = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Cerebro" / "mcp-state.json"

MODES = (
    "quick",
    "source",
    "release",
    "full",
    "patch",
    "pipeline",
    "standards",
    "runtime",
)

RESET = "\033[0m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
GREY = "\033[90m"
CYAN = "\033[96m"
BOLD = "\033[1m"


@dataclass
class Check:
    name: str
    status: str
    details: str = ""
    commit: str = ""


def enable_terminal_colors() -> bool:
    if not sys.stdout.isatty():
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


USE_COLOR = enable_terminal_colors()


def color(text: str, code: str) -> str:
    return f"{code}{text}{RESET}" if USE_COLOR else text


def status_visual(status: str) -> tuple[str, str]:
    values = {
        "pass": ("●", GREEN),
        "warning": ("●", YELLOW),
        "fail": ("●", RED),
        "not_checked": ("○", GREY),
    }
    return values.get(status, ("?", GREY))


def api_json(repo: str, endpoint: str) -> Any:
    url = f"https://api.github.com/repos/{repo}/{endpoint}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "Cerebro-Valider-0.1",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def raw_text(repo: str, path: str) -> str:
    url = f"https://raw.githubusercontent.com/{repo}/{BRANCH}/{path}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Cerebro-Valider-0.1"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.read().decode("utf-8")


def remote_commit(repo: str) -> str:
    data = api_json(repo, f"commits/{BRANCH}")
    return str(data["sha"])


def remote_yaml(repo: str, path: str) -> dict[str, Any]:
    data = yaml.safe_load(raw_text(repo, path))
    if not isinstance(data, dict):
        raise ValueError(f"{repo}/{path} is not a mapping")
    return data


def validate_source() -> tuple[Check, dict[str, Any]]:
    try:
        commit = remote_commit(SOURCE_REPO)
        manifest = remote_yaml(SOURCE_REPO, "cerebro.yaml")
        registry = remote_yaml(SOURCE_REPO, "standards/standards.yaml")
        documents = {item.get("id"): item for item in registry.get("documents", [])}

        errors = []
        if manifest.get("source", {}).get("repository") != SOURCE_REPO:
            errors.append("repository identity")
        if manifest.get("source", {}).get("authority") != "sole":
            errors.append("sole authority")
        governance = manifest.get("governance", {})
        if governance.get("single_source_of_truth") is not True:
            errors.append("single source of truth")
        if governance.get("common_validation_entrypoint") != "valider":
            errors.append("valider entrypoint")
        for standard_id in ("STD-MCP", "STD-SOURCE", "STD-PUBLICATION", "STD-QUALITY", "STD-VALIDER"):
            if standard_id not in documents:
                errors.append(standard_id)

        if errors:
            return Check("Source", "fail", ", ".join(errors), commit[:8]), {
                "manifest": manifest,
                "registry": registry,
            }

        return Check("Source", "pass", "Cerebro Source 1.0", commit[:8]), {
            "manifest": manifest,
            "registry": registry,
        }
    except Exception as exc:
        return Check("Source", "fail", str(exc)), {}


def validate_release() -> tuple[Check, dict[str, Any]]:
    try:
        commit = remote_commit(RELEASE_REPO)
        manifest = remote_yaml(RELEASE_REPO, "cerebro.yaml")
        registry = remote_yaml(RELEASE_REPO, "standards/standards.yaml")
        documents = {item.get("id"): item for item in registry.get("documents", [])}

        errors = []
        authority = manifest.get("source_authority", {})
        if authority.get("identity") != "Cerebro Source 1.0":
            errors.append("Source identity")
        if authority.get("authority") != "sole":
            errors.append("sole authority")
        if authority.get("implementation_authoritative") is not False:
            errors.append("implementation authority")
        if registry.get("standards_engine", {}).get("role") != "derived-policy-registry":
            errors.append("derived registry")
        for standard_id in (
            "STD-MCP",
            "STD-SOURCE",
            "STD-BUILDER",
            "STD-PUBLICATION",
            "STD-QUALITY",
            "STD-VALIDER",
        ):
            if standard_id not in documents:
                errors.append(standard_id)

        required_files = (
            "tooling/quality/quality_gate.py",
            "tooling/patch/repository_publisher.py",
            "tooling/validation/valider.py",
        )
        for path in required_files:
            raw_text(RELEASE_REPO, path)

        if errors:
            return Check("Release", "fail", ", ".join(errors), commit[:8]), {
                "manifest": manifest,
                "registry": registry,
            }

        version = manifest.get("release", {}).get("version", "unknown")
        return Check("Release", "pass", f"Release {version}", commit[:8]), {
            "manifest": manifest,
            "registry": registry,
        }
    except Exception as exc:
        return Check("Release", "fail", str(exc)), {}


def validate_sync(
    source_data: dict[str, Any],
    release_data: dict[str, Any],
) -> Check:
    if not source_data or not release_data:
        return Check("Sync", "not_checked", "Repository validation incomplete")

    source_ids = {
        item.get("id")
        for item in source_data["registry"].get("documents", [])
    }
    release_ids = {
        item.get("id")
        for item in release_data["registry"].get("documents", [])
    }

    authoritative = {"STD-MCP", "STD-SOURCE", "STD-PUBLICATION", "STD-QUALITY", "STD-VALIDER"}
    missing = authoritative - release_ids
    if not authoritative.issubset(source_ids):
        return Check("Sync", "fail", "Source authority registry incomplete")
    if missing:
        return Check("Sync", "fail", "Release missing " + ", ".join(sorted(missing)))
    return Check("Sync", "pass", "Authoritative standards represented")


def mcp_check() -> Check:
    try:
        manifest = remote_yaml(SOURCE_REPO, "mcp/manifest.yaml")
        if manifest.get("mcp", {}).get("level") != 1:
            return Check("MCP", "fail", "MCP level is not 1")
        if manifest.get("mcp", {}).get("default_state") != "active":
            return Check("MCP", "fail", "MCP is not active by default")

        state = "active"
        if MCP_STATE_FILE.is_file():
            local = json.loads(MCP_STATE_FILE.read_text(encoding="utf-8"))
            state = local.get("state", "active")

        if state == "inactive":
            return Check("MCP", "warning", "Inactive by user command")
        return Check("MCP", "pass", "Level 1 · Active")
    except Exception as exc:
        return Check("MCP", "fail", str(exc))


def gate_check(name: str, path: str) -> Check:
    try:
        raw_text(RELEASE_REPO, path)
        return Check(name, "pass", "Present in Release")
    except Exception as exc:
        return Check(name, "fail", str(exc))


def run_local(name: str, arguments: list[str]) -> Check:
    process = subprocess.run(
        [sys.executable, "cerebro_tool.py", *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    details = (process.stdout + process.stderr).strip()
    if process.returncode == 0:
        return Check(name, "pass", "Local command passed")
    return Check(name, "fail", details[-500:] or f"exit {process.returncode}")


def quick_checks(target: str = "both") -> list[Check]:
    checks: list[Check] = [mcp_check()]
    source_check = Check("Source", "not_checked")
    release_check = Check("Release", "not_checked")
    source_data: dict[str, Any] = {}
    release_data: dict[str, Any] = {}

    if target in ("both", "source"):
        source_check, source_data = validate_source()
        checks.append(source_check)

    if target in ("both", "release"):
        release_check, release_data = validate_release()
        checks.append(release_check)

    if target == "both":
        checks.append(validate_sync(source_data, release_data))
        checks.append(gate_check("Standards", "standards/standards.yaml"))
        checks.append(gate_check("Quality Gate", "tooling/quality/quality_gate.py"))
        checks.append(
            gate_check(
                "Publication Gate",
                "tooling/patch/repository_publisher.py",
            )
        )

    return checks


def render(checks: list[Check], mode: str) -> None:
    width = 52
    title = f"CEREBRO VALIDATION · {mode.upper()}"
    print()
    print(color("╭" + "─" * width + "╮", CYAN))
    print(color("│ ", CYAN) + color(title.ljust(width - 2), BOLD) + color(" │", CYAN))
    print(color("├" + "─" * width + "┤", CYAN))

    for item in checks:
        symbol, tone = status_visual(item.status)
        status_text = {
            "pass": "PASS",
            "warning": "WARNING",
            "fail": "FAIL",
            "not_checked": "NOT CHECKED",
        }.get(item.status, item.status.upper())

        commit = f" {item.commit}" if item.commit else ""
        left = f"{symbol} {item.name}"
        right = f"{status_text}{commit}"
        gap = max(1, width - 2 - len(left) - len(right))
        print(
            color("│ ", CYAN)
            + color(left, tone)
            + " " * gap
            + color(right, tone)
            + color(" │", CYAN)
        )

    print(color("├" + "─" * width + "┤", CYAN))
    failures = [item for item in checks if item.status == "fail"]
    warnings = [item for item in checks if item.status == "warning"]
    if failures:
        result = "SYSTEM INVALID"
        tone = RED
    elif warnings:
        result = "SYSTEM VALID WITH WARNINGS"
        tone = YELLOW
    else:
        result = "SYSTEM VALID"
        tone = GREEN
    print(
        color("│ ", CYAN)
        + color(("RESULT: " + result).ljust(width - 2), tone)
        + color(" │", CYAN)
    )
    print(color("╰" + "─" * width + "╯", CYAN))

    for item in checks:
        if item.status != "pass" and item.details:
            print(f"{item.name}: {item.details}")
    print()


def report_json(checks: list[Check], mode: str) -> dict[str, Any]:
    failed = [item.name for item in checks if item.status == "fail"]
    warnings = [item.name for item in checks if item.status == "warning"]
    return {
        "schema": "cerebro-valider-report/v0.1",
        "mode": mode,
        "result": "fail" if failed else "warning" if warnings else "pass",
        "failed": failed,
        "warnings": warnings,
        "checks": [asdict(item) for item in checks],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Cerebro common validation command")
    parser.add_argument("mode", nargs="?", default="quick", choices=MODES)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--patch-root")
    args = parser.parse_args()

    mode = args.mode
    if mode == "source":
        checks = quick_checks("source")
    elif mode == "release":
        checks = quick_checks("release")
    elif mode == "standards":
        checks = [run_local("Standards", ["standards"])]
    elif mode == "pipeline":
        checks = [run_local("Pipeline", ["pipeline", "release"])]
    elif mode == "runtime":
        checks = [
            run_local("Runtime Tests", ["test"]),
            run_local("Runtime Validation", ["validate"]),
        ]
    elif mode == "patch":
        if not args.patch_root:
            checks = [Check("Patch", "fail", "--patch-root is required")]
        else:
            checks = [
                run_local(
                    "Patch",
                    ["patch-validate", "--patch-root", args.patch_root],
                )
            ]
    elif mode == "full":
        checks = quick_checks("both")
        checks.extend([
            run_local("Local Standards", ["standards"]),
            run_local("Local Checksum", ["checksum"]),
            run_local("Local Validation", ["validate"]),
            run_local("Release Pipeline", ["pipeline", "release"]),
        ])
    else:
        checks = quick_checks("both")

    report = report_json(checks, mode)
    if args.json_output:
        print(json.dumps(report, indent=2))
    else:
        render(checks, mode)

    return 0 if report["result"] == "pass" else 10


if __name__ == "__main__":
    raise SystemExit(main())
