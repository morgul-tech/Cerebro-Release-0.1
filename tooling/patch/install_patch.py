#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_INSTALL = 6

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from locate_cerebro import resolve


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data.get("schema") != "cerebro-patch-manifest/v0.1":
        raise ValueError("Unsupported patch manifest schema.")
    return data


def resolve_destination(raw: str, repository_root: Path, scripts_root: Path) -> Path:
    normalized = raw.replace("\\", "/")
    if normalized.startswith("{REPOSITORY_ROOT}/"):
        return repository_root / normalized.removeprefix("{REPOSITORY_ROOT}/")
    if normalized.startswith("{SCRIPTS_ROOT}/"):
        return scripts_root / normalized.removeprefix("{SCRIPTS_ROOT}/")
    raise ValueError(f"Unsupported destination root: {raw}")


def verify_sources(patch_root: Path, files: list[dict[str, Any]]) -> None:
    failures = []
    for item in files:
        source = patch_root / item["source"]
        if not source.is_file():
            failures.append(f"Missing source: {item['source']}")
            continue
        actual = sha256(source)
        if item.get("sha256") and actual != item["sha256"]:
            failures.append(f"Checksum mismatch: {item['source']}")
    if failures:
        raise RuntimeError("\n".join(failures))


def backup_existing(destinations: list[Path], backup_root: Path) -> None:
    for destination in destinations:
        if destination.is_file():
            safe_name = destination.drive.replace(":", "") + destination.as_posix().replace(":", "")
            backup = backup_root / safe_name.lstrip("/")
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destination, backup)


def install_files(
    patch_root: Path,
    repository_root: Path,
    scripts_root: Path,
    manifest: dict[str, Any],
) -> list[Path]:
    files = manifest.get("files", [])
    destinations = [
        resolve_destination(item["destination"], repository_root, scripts_root)
        for item in files
    ]

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_root = repository_root / "backups" / f"patch-{manifest['patch']['id']}-{timestamp}"
    backup_existing(destinations, backup_root)

    installed: list[Path] = []
    for item, destination in zip(files, destinations):
        source = patch_root / item["source"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if sha256(destination) != item["sha256"]:
            raise RuntimeError(f"Post-copy checksum mismatch: {destination}")
        installed.append(destination)

    return installed


def run_verification(repository_root: Path, commands: list[list[str]]) -> None:
    for command in commands:
        resolved = [sys.executable if token == "{PYTHON}" else token for token in command]
        print()
        print("VERIFY:", " ".join(resolved))
        result = subprocess.run(resolved, cwd=repository_root)
        if result.returncode != 0:
            raise RuntimeError(
                f"Verification failed with exit code {result.returncode}: "
                + " ".join(resolved)
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Install a Cerebro patch package")
    parser.add_argument("--patch-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--repository-root")
    parser.add_argument("--scripts-root")
    parser.add_argument("--non-interactive", action="store_true")
    args = parser.parse_args()

    patch_root = Path(args.patch_root).resolve()
    manifest_path = patch_root / "PATCH_MANIFEST.yaml"

    try:
        if args.repository_root and args.scripts_root:
            repository_root = Path(args.repository_root).resolve()
            scripts_root = Path(args.scripts_root).resolve()
        else:
            repository_root, scripts_root = resolve(interactive=not args.non_interactive)

        print(f"[PASS] Repository: {repository_root}")
        print(f"[PASS] Scripts: {scripts_root}")

        manifest = load_manifest(manifest_path)
        verify_sources(patch_root, manifest.get("files", []))
        installed = install_files(
            patch_root, repository_root, scripts_root, manifest
        )
        run_verification(repository_root, manifest.get("verification", []))
    except Exception as exc:
        print()
        print("[FAIL] Patch installation failed.")
        print(exc)
        return EXIT_INSTALL

    print()
    print("[PASS] Patch installation completed.")
    print(f"Installed files: {len(installed)}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
