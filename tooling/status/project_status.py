#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEPTH_ALIASES = {"brief": "brief", "kort": "brief", "liten": "brief", "standard": "standard", "deep": "deep", "dyp": "deep", "full": "deep", "detaljert": "deep"}


def find_workspace(start: Path = ROOT) -> Path:
    configured = os.environ.get("CEREBRO_WORKSPACE")
    if configured:
        return Path(configured).resolve()
    for candidate in (start, *start.parents):
        if (candidate / "Reports").is_dir() and (candidate / "Source").is_dir():
            return candidate
    return start


def git_output(repo: Path, *arguments: str) -> str:
    if not (repo / ".git").exists():
        return ""
    process = subprocess.run(
        ["git", "-c", f"safe.directory={repo}", *arguments],
        cwd=repo,
        text=True,
        capture_output=True,
    )
    return process.stdout.strip() if process.returncode == 0 else ""


def repository_health(name: str, repo: Path) -> dict[str, Any]:
    head = git_output(repo, "rev-parse", "HEAD")
    remote = git_output(repo, "rev-parse", "origin/main")
    dirty = bool(git_output(repo, "status", "--porcelain"))
    return {"name": name, "path": str(repo), "head": head, "origin_main": remote, "clean": not dirty, "synchronized": bool(head and remote and head == remote and not dirty)}


def log_entries(name: str, repo: Path, limit: int = 3) -> list[dict[str, str]]:
    output = git_output(repo, "log", f"-{limit}", "--pretty=format:%H%x1f%s")
    entries = []
    for line in output.splitlines():
        if "\x1f" in line:
            commit, subject = line.split("\x1f", 1)
            entries.append({"repository": name, "commit": commit, "subject": subject})
    return entries


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def collect_notes(reports: Path, limit: int) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    working: list[dict[str, str]] = []
    loose: list[dict[str, str]] = []
    if not reports.is_dir():
        return working, loose
    candidates = sorted((p for p in reports.rglob("*") if p.suffix.lower() in {".md", ".yaml", ".yml", ".json"}), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")[:6000]
        except OSError:
            continue
        status = ""
        try:
            if path.suffix.lower() in {".yaml", ".yml", ".json"}:
                document = yaml.safe_load(text)
                if isinstance(document, dict):
                    status = str(document.get("status", ""))
            else:
                match = re.search(r"(?im)^status:\s*(.+)$", text[:1500])
                status = match.group(1) if match else ""
        except (ValueError, yaml.YAMLError):
            status = ""
        lowered_status = status.casefold()
        lowered_name = path.name.casefold()
        relative = path.relative_to(reports.parent).as_posix()
        item = {"path": relative, "name": path.stem}
        if any(marker in lowered_status for marker in ("draft", "proposed")):
            loose.append(item)
        elif any(marker in lowered_status for marker in ("locked", "in_progress", "active", "refined_recommended")) or "arbeidsnotat" in lowered_name:
            working.append(item)
        if len(working) >= limit and len(loose) >= limit:
            break
    return working[:limit], loose[:limit]


def recommendations(roadmap: dict[str, Any]) -> list[dict[str, Any]]:
    next_action = roadmap.get("next_action", {})
    action = next_action.get("action", "Complete the active authorized implementation.")
    return [
        {"weight": 3, "action": action, "reason": "This is the declared next action for the active roadmap phase."},
        {"weight": 2, "action": "Continue the top-down terminology levels.", "reason": "A shared language is a dependency for terminal, MCP, and HUD."},
        {"weight": 1, "action": "Add status since last after the shared status model is stable.", "reason": "Useful QoL that does not block the common status contract."},
    ]


def build_status(workspace: Path, depth: str = "standard", scope: str | None = None) -> dict[str, Any]:
    source = workspace / "Source" / "Cerebro_Source_v1.0"
    release = workspace / "Client" / "Cerebro-Release-0.1"
    roadmap_path = workspace / "Reports" / "Planning" / "Cerebro_Roadmap_v1.yaml"
    roadmap = load_yaml(roadmap_path)
    phases = roadmap.get("phases", [])
    active = [phase for phase in phases if phase.get("status") == "IN_PROGRESS"]
    note_limit = 3 if depth == "standard" else 15
    working_notes, loose_thoughts = collect_notes(workspace / "Reports", note_limit)
    report: dict[str, Any] = {
        "schema": "cerebro-project-status/v1",
        "depth": depth,
        "scope": scope,
        "system_health": [repository_health("Source", source), repository_health("Release", release)],
        "latest_implementations": log_entries("Source", source) + log_entries("Release", release),
        "active_implementation": active,
        "next_implementation": roadmap.get("next_action", {}),
        "working_notes": working_notes,
        "loose_thoughts": loose_thoughts,
        "blockers": [roadmap.get("next_action", {}).get("blocker")] if roadmap.get("next_action", {}).get("blocker") not in (None, "none") else [],
        "recommendations": recommendations(roadmap),
        "evidence": {"roadmap": str(roadmap_path), "workspace": str(workspace)},
    }
    if depth == "brief":
        report["latest_implementations"] = report["latest_implementations"][:2]
        report["working_notes"] = []
        report["loose_thoughts"] = []
        report["recommendations"] = report["recommendations"][:1]
        report["evidence"] = {}
    if scope:
        needle = scope.casefold()
        report["latest_implementations"] = [item for item in report["latest_implementations"] if needle in (item["repository"] + " " + item["subject"]).casefold()]
        report["working_notes"] = [item for item in report["working_notes"] if needle in (item["path"] + " " + item["name"]).casefold()]
        report["loose_thoughts"] = [item for item in report["loose_thoughts"] if needle in (item["path"] + " " + item["name"]).casefold()]
    return report


def render(report: dict[str, Any]) -> None:
    print(f"CEREBRO STATUS · {report['depth'].upper()}")
    if report.get("scope"):
        print(f"Scope: {report['scope']}")
    print("\nHealth")
    for item in report["system_health"]:
        state = "SYNC" if item["synchronized"] else "CHECK"
        print(f"- {item['name']}: {state} {item['head'][:8] if item['head'] else 'unknown'}")
    print("\nLatest")
    for item in report["latest_implementations"]:
        print(f"- {item['repository']} {item['commit'][:8]} · {item['subject']}")
    print("\nActive")
    for item in report["active_implementation"]:
        print(f"- {item.get('name', item.get('id', 'unknown'))}")
    print("\nNext")
    print(f"- {report['next_implementation'].get('action', 'Not declared')}")
    if report["working_notes"]:
        print("\nWorking notes")
        for item in report["working_notes"]:
            print(f"- {item['path']}")
    if report["loose_thoughts"]:
        print("\nLoose thoughts")
        for item in report["loose_thoughts"]:
            print(f"- {item['path']}")
    print("\nRecommendations")
    for item in report["recommendations"]:
        print(f"- [{item['weight']}] {item['action']} — {item['reason']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Show Cerebro project status")
    parser.add_argument("depth", nargs="?", default="standard")
    parser.add_argument("--scope")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--workspace")
    args = parser.parse_args()
    depth = DEPTH_ALIASES.get(args.depth.casefold())
    if depth is None:
        parser.error(f"Unsupported depth: {args.depth}")
    report = build_status(Path(args.workspace).resolve() if args.workspace else find_workspace(), depth, args.scope)
    print(json.dumps(report, indent=2, ensure_ascii=False) if args.json_output else "", end="") if args.json_output else render(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
