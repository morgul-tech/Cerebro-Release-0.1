#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

HERE = Path(__file__).resolve().parent
RELEASE_ROOT = HERE.parents[1]
SCHEMA_CANDIDATES = (
    HERE.parent / "schemas" / "patch-manifest.schema.yaml",
    RELEASE_ROOT / "schemas" / "patch-manifest.schema.yaml",
)
SCHEMA = next((path for path in SCHEMA_CANDIDATES if path.is_file()), SCHEMA_CANDIDATES[0])
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from locate_cerebro import resolve


class Result(IntEnum):
    SUCCESS = 0
    ALREADY_APPLIED = 2
    BLOCKED_PREREQUISITE = 20
    PATCH_ALREADY_RUNNING = 21
    BASELINE_MISMATCH = 22
    UNKNOWN_AUTHORITATIVE_STATE = 23
    VALIDATION_FAILED = 24
    QUALITY_GATE_FAILED = 25
    PUBLICATION_BLOCKED = 26
    FAILED_ROLLED_BACK = 30
    FAILED_RECOVERY_REQUIRED = 31
    INVALID_PACKAGE = 40


class PatchError(RuntimeError):
    def __init__(self, result: Result, message: str):
        super().__init__(message)
        self.result = result


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
        schema = yaml.safe_load(SCHEMA.read_text(encoding="utf-8"))
        issues = sorted(Draft202012Validator(schema).iter_errors(manifest), key=lambda e: list(e.path))
    except Exception as exc:
        raise PatchError(Result.INVALID_PACKAGE, f"Manifest could not be parsed: {exc}") from exc
    if issues:
        detail = "; ".join(f"{'/'.join(map(str, i.path))}: {i.message}" for i in issues)
        raise PatchError(Result.INVALID_PACKAGE, detail)
    return manifest


def contained(root: Path, candidate: Path) -> Path:
    resolved_root = root.resolve()
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise PatchError(Result.INVALID_PACKAGE, f"Destination escapes declared root: {candidate}") from exc
    if resolved == resolved_root:
        raise PatchError(Result.INVALID_PACKAGE, "Destination cannot be the declared root itself")
    return resolved


def resolve_destination(raw: str, repo: Path, scripts: Path) -> Path:
    value = raw.replace("\\", "/")
    roots = {"{REPOSITORY_ROOT}/": repo, "{SCRIPTS_ROOT}/": scripts}
    for prefix, root in roots.items():
        if value.startswith(prefix):
            relative = value.removeprefix(prefix)
            if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts or ":" in relative:
                raise PatchError(Result.INVALID_PACKAGE, f"Unsafe destination: {raw}")
            return contained(root, root / Path(relative))
    raise PatchError(Result.INVALID_PACKAGE, f"Unsupported destination root: {raw}")


def verify_sources(root: Path, files: list[dict[str, Any]]) -> None:
    for item in files:
        source = contained(root, root / item["source"])
        if not source.is_file() or sha256(source).lower() != item["sha256"].lower():
            raise PatchError(Result.INVALID_PACKAGE, f"Payload missing or checksum mismatch: {item['source']}")


def git_output(repo: Path, *args: str) -> str:
    try:
        result = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True)
    except OSError as exc:
        raise PatchError(Result.BLOCKED_PREREQUISITE, "Git is required to verify authority") from exc
    if result.returncode != 0:
        raise PatchError(Result.UNKNOWN_AUTHORITATIVE_STATE, (result.stdout + result.stderr).strip())
    return result.stdout.strip()


def normalize_repository_url(value: str) -> str:
    value = value.strip().removesuffix("/").removesuffix(".git")
    if value.startswith("git@github.com:"):
        value = "https://github.com/" + value.removeprefix("git@github.com:")
    return value.lower()


def verify_authority(repo: Path, authoritative: dict[str, str]) -> None:
    actual_url = normalize_repository_url(git_output(repo, "remote", "get-url", "origin"))
    actual_branch = git_output(repo, "rev-parse", "--abbrev-ref", "HEAD")
    actual_commit = git_output(repo, "rev-parse", "HEAD").lower()
    expected_url = normalize_repository_url(authoritative["repository_url"])
    if (actual_url, actual_branch, actual_commit) != (
        expected_url,
        authoritative["branch"],
        authoritative["commit"].lower(),
    ):
        raise PatchError(Result.UNKNOWN_AUTHORITATIVE_STATE, "Repository URL, branch, or commit conflicts with authoritative evidence")


def destination_map(manifest: dict[str, Any], repo: Path, scripts: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for item in manifest["files"]:
        raw = item["destination"]
        if raw in result:
            raise PatchError(Result.INVALID_PACKAGE, f"Duplicate destination: {raw}")
        result[raw] = resolve_destination(raw, repo, scripts)
    return result


def runtime_state(path: Path) -> tuple[str, str | None]:
    if not path.exists():
        return "absent", None
    if not path.is_file():
        raise PatchError(Result.BASELINE_MISMATCH, f"Destination is not a file: {path}")
    return "present", sha256(path)


def verify_baseline(manifest: dict[str, Any], targets: dict[str, Path]) -> None:
    declared = {item["destination"]: item for item in manifest["baseline"]}
    if set(declared) != set(targets):
        raise PatchError(Result.INVALID_PACKAGE, "Baseline must cover every destination exactly once")
    for raw, path in targets.items():
        expected = declared[raw]
        state, digest = runtime_state(path)
        if state != expected["state"] or (state == "present" and digest.lower() != expected["sha256"].lower()):
            raise PatchError(Result.BASELINE_MISMATCH, f"Runtime baseline differs for {raw}")


def already_applied(root: Path, manifest: dict[str, Any], targets: dict[str, Path]) -> bool:
    for item in manifest["files"]:
        target = targets[item["destination"]]
        if item["operation"] == "delete":
            if target.exists():
                return False
        else:
            source = contained(root, root / item["source"])
            if not target.is_file() or sha256(target) != sha256(source):
                return False
    return True


FORBIDDEN_TOKEN = re.compile(r"&&|\|\||[|<>`]|\$\(|%[^%]+%|(?:^|[/\\])\.\.(?:[/\\]|$)")


def run_verification(repo: Path, commands: list[list[str]]) -> None:
    for command in commands:
        if not command or command[0] != "{PYTHON}" or any(FORBIDDEN_TOKEN.search(token) for token in command):
            raise PatchError(Result.INVALID_PACKAGE, f"Unsupported verification command: {command}")
        resolved = [sys.executable, *command[1:]]
        result = subprocess.run(resolved, cwd=repo)
        if result.returncode != 0:
            raise PatchError(Result.VALIDATION_FAILED, f"Verification exited {result.returncode}: {command}")


class ExecutionLock:
    def __init__(self, repo: Path):
        identity = hashlib.sha256(str(repo.resolve()).encode()).hexdigest()[:16]
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Cerebro" / "locks"
        base.mkdir(parents=True, exist_ok=True)
        self.path = base / f"patch-{identity}.lock"
        self.fd: int | None = None

    def __enter__(self) -> "ExecutionLock":
        try:
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(self.fd, f"pid={os.getpid()}\n".encode())
        except FileExistsError as exc:
            raise PatchError(Result.PATCH_ALREADY_RUNNING, f"Lock exists: {self.path}") from exc
        return self

    def __exit__(self, *_: object) -> None:
        if self.fd is not None:
            os.close(self.fd)
        self.path.unlink(missing_ok=True)


def backup_and_apply(
    root: Path,
    manifest: dict[str, Any],
    targets: dict[str, Path],
    journal: list[tuple[Path, Path | None]],
) -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Cerebro" / "backups"
    backup = base / f"patch-{manifest['patch']['id']}-{datetime.now():%Y%m%d-%H%M%S-%f}"
    backup.mkdir(parents=True, exist_ok=False)
    for index, item in enumerate(manifest["files"]):
        target = targets[item["destination"]]
        saved: Path | None = None
        if target.is_file():
            saved = backup / f"{index:04d}.bak"
            shutil.copy2(target, saved)
        journal.append((target, saved))
        if item["operation"] == "delete":
            target.unlink(missing_ok=True)
        else:
            source = contained(root, root / item["source"])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            if sha256(target) != item["sha256"]:
                raise PatchError(Result.VALIDATION_FAILED, f"Post-copy checksum mismatch: {target}")
    return backup


def rollback(journal: list[tuple[Path, Path | None]]) -> bool:
    ok = True
    for target, saved in reversed(journal):
        try:
            if saved is None:
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(saved, target)
        except Exception:
            ok = False
    return ok


def run_quality_gate(root: Path, repo: Path) -> None:
    result = subprocess.run([sys.executable, str(repo / "tooling/quality/quality_gate.py"), "--patch-root", str(root)], cwd=repo)
    if result.returncode != 0:
        raise PatchError(Result.QUALITY_GATE_FAILED, f"Quality Gate exited {result.returncode}")


def publish(root: Path, repo: Path, manifest: dict[str, Any]) -> None:
    if manifest["publication"]["enabled"] is not True:
        raise PatchError(Result.PUBLICATION_BLOCKED, "Publication is disabled by manifest")
    result = subprocess.run([sys.executable, str(root / "installer/repository_publisher.py"), "--repository-root", str(repo), "--manifest", str(root / "PATCH_MANIFEST.yaml")], cwd=repo)
    if result.returncode != 0:
        raise PatchError(Result.PUBLICATION_BLOCKED, f"Publication Gate exited {result.returncode}")


def record_execution(
    manifest: dict[str, Any],
    result: Result,
    backup: Path | None,
    repo: Path,
    detail: str = "",
) -> None:
    report_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Cerebro" / "reports" / "patch"
    report_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "cerebro-patch-execution/v1.0",
        "patch": manifest["patch"]["id"],
        "result": result.name,
        "exit_code": int(result),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "authoritative": manifest["authoritative"],
        "backup": str(backup) if backup else None,
        "detail": detail,
    }
    target = report_dir / f"{manifest['patch']['id']}-{datetime.now():%Y%m%d-%H%M%S-%f}.json"
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    controller = repo / "tooling" / "plc" / "controller.py"
    if controller.is_file():
        try:
            environment = os.environ.copy()
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            subprocess.run(
                [
                    sys.executable,
                    str(controller),
                    str(target),
                    "--record-dir",
                    str(report_dir.parent / "plc"),
                ],
                cwd=repo,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
        except Exception:
            # PLC is observational and must never alter the patch result.
            pass


def execute(root: Path, repo: Path, scripts: Path, manifest: dict[str, Any], install_only: bool) -> Result:
    verify_sources(root, manifest["files"])
    targets = destination_map(manifest, repo, scripts)
    with ExecutionLock(repo):
        verify_authority(repo, manifest["authoritative"])
        if already_applied(root, manifest, targets):
            record_execution(manifest, Result.ALREADY_APPLIED, None, repo)
            return Result.ALREADY_APPLIED
        verify_baseline(manifest, targets)
        backup: Path | None = None
        journal: list[tuple[Path, Path | None]] = []
        try:
            # Recheck under the exclusive lock immediately before the first mutation.
            verify_baseline(manifest, targets)
            backup = backup_and_apply(root, manifest, targets, journal)
            run_verification(repo, manifest["verification"])
            if not install_only:
                run_quality_gate(root, repo)
                publish(root, repo, manifest)
            record_execution(manifest, Result.SUCCESS, backup, repo)
            return Result.SUCCESS
        except Exception as exc:
            if rollback(journal):
                record_execution(manifest, Result.FAILED_ROLLED_BACK, backup, repo, str(exc))
                raise PatchError(Result.FAILED_ROLLED_BACK, str(exc)) from exc
            record_execution(manifest, Result.FAILED_RECOVERY_REQUIRED, backup, repo, str(exc))
            raise PatchError(Result.FAILED_RECOVERY_REQUIRED, str(exc)) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Install a Cerebro PATCH Specification v1.0 package")
    parser.add_argument("--patch-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--repository-root")
    parser.add_argument("--scripts-root")
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--install-only", action="store_true")
    args = parser.parse_args()
    root = Path(args.patch_root).resolve()
    try:
        if args.repository_root and args.scripts_root:
            repo, scripts = Path(args.repository_root).resolve(), Path(args.scripts_root).resolve()
        else:
            repo, scripts = resolve(interactive=not args.non_interactive)
        manifest = load_manifest(root / "PATCH_MANIFEST.yaml")
        result = execute(root, repo, scripts, manifest, args.install_only)
        print(f"[{result.name}] Patch operation completed with exit code {int(result)}")
        return int(result)
    except PatchError as exc:
        print(f"[{exc.result.name}] {exc}")
        return int(exc.result)
    except Exception as exc:
        print(f"[{Result.BLOCKED_PREREQUISITE.name}] {exc}")
        return int(Result.BLOCKED_PREREQUISITE)


if __name__ == "__main__":
    raise SystemExit(main())
