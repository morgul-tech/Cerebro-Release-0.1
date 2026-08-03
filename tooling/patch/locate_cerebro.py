#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Iterable

APPDATA = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
SETTINGS_DIR = APPDATA / "Cerebro"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"

DEFAULT_CANDIDATES = [
    Path(r"D:\Cerebro\Client\Cerebro-Release-0.1"),
    Path(r"C:\Cerebro\Client\Cerebro-Release-0.1"),
]


def is_repository(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / "cerebro.yaml").is_file()
        and (path / "cerebro_tool.py").is_file()
    )


def load_settings() -> dict:
    if not SETTINGS_FILE.is_file():
        return {}
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(repository_root: Path, scripts_root: Path) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "cerebro-local-settings/v0.1",
        "repository_root": str(repository_root),
        "scripts_root": str(scripts_root),
    }
    SETTINGS_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def configured_paths() -> tuple[Path | None, Path | None]:
    data = load_settings()
    repository = Path(data["repository_root"]) if data.get("repository_root") else None
    scripts = Path(data["scripts_root"]) if data.get("scripts_root") else None
    return repository, scripts


def candidates(extra: Iterable[Path] = ()) -> list[Path]:
    result: list[Path] = []
    configured, _ = configured_paths()
    if configured:
        result.append(configured)
    result.extend(extra)
    result.extend(DEFAULT_CANDIDATES)

    unique: list[Path] = []
    seen: set[str] = set()
    for item in result:
        key = str(item).lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def discover(extra: Iterable[Path] = ()) -> Path | None:
    for candidate in candidates(extra):
        if is_repository(candidate):
            return candidate.resolve()
    return None


def prompt_repository() -> Path:
    print()
    print("Cerebro repository was not found automatically.")
    print("Enter the full path to Cerebro-Release-0.1.")
    while True:
        raw = input("Repository path: ").strip().strip('"')
        path = Path(raw)
        if is_repository(path):
            return path.resolve()
        print()
        print("[FAIL] This folder is not a valid Cerebro repository.")
        print("Required files: cerebro.yaml and cerebro_tool.py")


def prompt_scripts(default: Path | None = None) -> Path:
    suggested = default or Path(r"D:\Cerebro\scripts")
    print()
    raw = input(f"Scripts path [{suggested}]: ").strip().strip('"')
    path = Path(raw) if raw else suggested
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def resolve(interactive: bool = True) -> tuple[Path, Path]:
    repository = discover()
    configured_repo, configured_scripts = configured_paths()

    if repository is None:
        if not interactive:
            raise FileNotFoundError("Cerebro repository could not be located.")
        repository = prompt_repository()

    scripts = configured_scripts
    if scripts is None or not scripts.is_dir():
        inferred = repository.parents[1] / "scripts" if len(repository.parents) >= 2 else None
        if inferred and inferred.is_dir():
            scripts = inferred.resolve()
        elif interactive:
            scripts = prompt_scripts(inferred)
        else:
            scripts = inferred or Path(r"D:\Cerebro\scripts")

    save_settings(repository, scripts)
    return repository, scripts


def main() -> int:
    parser = argparse.ArgumentParser(description="Locate and configure Cerebro paths")
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    if args.reset and SETTINGS_FILE.exists():
        SETTINGS_FILE.unlink()

    try:
        repository, scripts = resolve(interactive=not args.non_interactive)
    except Exception as exc:
        print(f"[FAIL] {exc}")
        return 3

    if args.json:
        print(json.dumps({
            "repository_root": str(repository),
            "scripts_root": str(scripts),
            "settings_file": str(SETTINGS_FILE),
        }))
    else:
        print(f"[PASS] Repository: {repository}")
        print(f"[PASS] Scripts: {scripts}")
        print(f"[PASS] Settings: {SETTINGS_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
