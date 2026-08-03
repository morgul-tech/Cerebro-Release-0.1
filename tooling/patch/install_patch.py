#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

EXIT_OK = 0
EXIT_INSTALL = 6

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from locate_cerebro import resolve


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data.get("schema") != "cerebro-patch-manifest/v0.1":
        raise ValueError("Unsupported patch manifest schema.")
    return data


def resolve_destination(raw: str, repo: Path, scripts: Path) -> Path:
    value = raw.replace("\\", "/")
    if value.startswith("{REPOSITORY_ROOT}/"):
        return repo / value.removeprefix("{REPOSITORY_ROOT}/")
    if value.startswith("{SCRIPTS_ROOT}/"):
        return scripts / value.removeprefix("{SCRIPTS_ROOT}/")
    raise ValueError(f"Unsupported destination: {raw}")


def verify_sources(root: Path, files: list[dict[str, Any]]) -> None:
    failures = []
    for item in files:
        source = root / item["source"]
        if not source.is_file():
            failures.append(f"Missing source: {item['source']}")
        elif sha256(source) != item["sha256"]:
            failures.append(f"Checksum mismatch: {item['source']}")
    if failures:
        raise RuntimeError("\n".join(failures))


def install_files(
    root: Path,
    repo: Path,
    scripts: Path,
    manifest: dict[str, Any],
) -> list[Path]:
    targets = [
        resolve_destination(item["destination"], repo, scripts)
        for item in manifest["files"]
    ]

    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    backup = (
        local_app_data
        / "Cerebro"
        / "backups"
        / f"patch-{manifest['patch']['id']}-{datetime.now():%Y%m%d-%H%M%S}"
    )

    for target in targets:
        if target.is_file():
            try:
                relative = target.relative_to(repo)
                saved = backup / "repository" / relative
            except ValueError:
                saved = backup / "external" / target.name
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)

    installed = []
    for item, target in zip(manifest["files"], targets):
        source = root / item["source"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if sha256(target) != item["sha256"]:
            raise RuntimeError(f"Post-copy checksum mismatch: {target}")
        installed.append(target)
    return installed


def run_verification(repo: Path, commands: list[list[str]]) -> None:
    for command in commands:
        resolved = [sys.executable if token == "{PYTHON}" else token for token in command]
        print("\nVERIFY:", " ".join(resolved))
        result = subprocess.run(resolved, cwd=repo)
        if result.returncode != 0:
            raise RuntimeError(
                f"Verification failed with exit code {result.returncode}: "
                + " ".join(resolved)
            )


def run_quality_gate(root: Path, repo: Path) -> None:
    gate = repo / "tooling" / "quality" / "quality_gate.py"
    result = subprocess.run(
        [
            sys.executable,
            str(gate),
            "--patch-root",
            str(root),
        ],
        cwd=repo,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Quality Gate blocked publication with exit code {result.returncode}."
        )


def publish(root: Path, repo: Path) -> None:
    publisher = root / "installer" / "repository_publisher.py"
    result = subprocess.run(
        [
            sys.executable,
            str(publisher),
            "--repository-root",
            str(repo),
            "--manifest",
            str(root / "PATCH_MANIFEST.yaml"),
        ],
        cwd=repo,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Publication Gate failed with exit code {result.returncode}."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Install a Cerebro patch")
    parser.add_argument("--patch-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--repository-root")
    parser.add_argument("--scripts-root")
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--install-only", action="store_true")
    args = parser.parse_args()

    root = Path(args.patch_root).resolve()

    try:
        if args.repository_root and args.scripts_root:
            repo = Path(args.repository_root).resolve()
            scripts = Path(args.scripts_root).resolve()
        else:
            repo, scripts = resolve(interactive=not args.non_interactive)

        print(f"[PASS] Repository: {repo}")
        print(f"[PASS] Scripts: {scripts}")

        manifest = load_manifest(root / "PATCH_MANIFEST.yaml")
        verify_sources(root, manifest["files"])
        installed = install_files(root, repo, scripts, manifest)
        run_verification(repo, manifest.get("verification", []))

        if not args.install_only:
            run_quality_gate(root, repo)
            publish(root, repo)
    except Exception as exc:
        print("\n[FAIL] Patch operation failed.")
        print(exc)
        return EXIT_INSTALL

    print("\n[PASS] Patch operation completed.")
    print(f"Installed files: {len(installed)}")
    print(
        "[INFO] Install-only mode completed."
        if args.install_only
        else "[PASS] Quality Gate and repository update verified."
    )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
