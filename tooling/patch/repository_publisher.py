#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

EXIT_OK = 0
EXIT_GIT = 7
EXIT_POLICY = 8


def locate_git() -> Path:
    located = shutil.which("git")
    candidates = [
        Path(located) if located else None,
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "cmd" / "git.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "git.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Git" / "cmd" / "git.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Git" / "cmd" / "git.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "GitHubDesktop" / "app-3.4.18" / "resources" / "app" / "git" / "cmd" / "git.exe",
    ]

    github_desktop = Path(os.environ.get("LOCALAPPDATA", "")) / "GitHubDesktop"
    if github_desktop.is_dir():
        for candidate in sorted(
            github_desktop.glob("app-*/resources/app/git/cmd/git.exe"),
            reverse=True,
        ):
            candidates.append(candidate)

    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate.resolve()

    raise FileNotFoundError(
        "git.exe was not found. Install Git for Windows or add Git to PATH."
    )


def run(
    git: Path,
    cwd: Path,
    *args: str,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(git), *args],
        cwd=cwd,
        text=True,
        capture_output=capture,
    )


def output(git: Path, cwd: Path, *args: str) -> str:
    result = run(git, cwd, *args, capture=True)
    if result.returncode != 0:
        detail = (result.stdout + result.stderr).strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def approved_paths(manifest: dict[str, Any]) -> list[str]:
    values: list[str] = []
    prefix = "{REPOSITORY_ROOT}/"

    for item in manifest.get("files", []):
        destination = str(item["destination"]).replace("\\", "/")
        if destination.startswith(prefix):
            values.append(destination.removeprefix(prefix))

    values.extend(
        str(path).replace("\\", "/")
        for path in manifest["publication"].get("generated_paths", [])
    )

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = value.strip("/")
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def copy_approved(source_root: Path, clone_root: Path, paths: list[str]) -> None:
    for relative in paths:
        source = source_root / relative
        destination = clone_root / relative

        if source.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        elif source.is_dir():
            if destination.exists():
                shutil.rmtree(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, destination)
        elif destination.exists():
            if destination.is_dir():
                shutil.rmtree(destination)
            else:
                destination.unlink()


def stage_approved(git: Path, clone_root: Path, paths: list[str]) -> None:
    for relative in paths:
        result = run(git, clone_root, "add", "-A", "--", relative)
        if result.returncode != 0:
            raise RuntimeError(f"Could not stage approved path: {relative}")


def confirm_remote(git: Path, clone_root: Path, remote: str, branch: str) -> None:
    local_sha = output(git, clone_root, "rev-parse", "HEAD")
    line = output(git, clone_root, "ls-remote", remote, f"refs/heads/{branch}")
    remote_sha = line.split()[0] if line else ""

    if local_sha != remote_sha:
        raise RuntimeError(
            f"Remote confirmation failed: local={local_sha}, "
            f"remote={remote_sha or 'missing'}"
        )

    print(f"[PASS] Remote commit confirmed: {local_sha}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish an approved Cerebro patch")
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()

    source_root = Path(args.repository_root).resolve()

    try:
        git = locate_git()
        print(f"[PASS] Git: {git}")

        manifest = yaml.safe_load(Path(args.manifest).read_text(encoding="utf-8"))
        publication = manifest.get("publication", {})

        if publication.get("enabled") is not True:
            raise ValueError("Publication is not enabled.")
        if publication.get("require_pipeline_pass") is not True:
            raise ValueError("Publication is not pipeline-gated.")

        repository_url = str(publication.get("repository_url", "")).strip()
        branch = str(publication.get("branch", "")).strip()
        remote = str(publication.get("remote", "origin")).strip()
        message = str(publication.get("commit_message", "")).strip()

        if not repository_url:
            raise ValueError("publication.repository_url is missing.")
        if not branch or branch == "current":
            raise ValueError("An explicit publication branch is required.")
        if not message:
            raise ValueError("Publication commit message is missing.")

        paths = approved_paths(manifest)
        if not paths:
            raise ValueError("No approved publication paths are declared.")

        with tempfile.TemporaryDirectory(prefix="cerebro-publish-") as temp:
            clone_root = Path(temp) / "repository"

            clone_result = run(
                git,
                Path(temp),
                "clone",
                "--branch",
                branch,
                "--single-branch",
                repository_url,
                str(clone_root),
            )
            if clone_result.returncode != 0:
                raise RuntimeError("git clone failed.")

            print("\nApproved publication paths:")
            for path in paths:
                print(f"- {path}")

            copy_approved(source_root, clone_root, paths)
            stage_approved(git, clone_root, paths)

            staged = output(git, clone_root, "diff", "--cached", "--name-status")
            if staged:
                print("\nStaged changes:")
                print(staged)

                commit_result = run(git, clone_root, "commit", "-m", message)
                if commit_result.returncode != 0:
                    raise RuntimeError(
                        "git commit failed. Ensure Git user.name and user.email are configured."
                    )
            else:
                print("[INFO] Remote repository already matches approved local files.")

            push_result = run(git, clone_root, "push", remote, branch)
            if push_result.returncode != 0:
                raise RuntimeError("git push failed.")

            confirm_remote(git, clone_root, remote, branch)

    except ValueError as exc:
        print(f"[FAIL] Publication policy: {exc}")
        return EXIT_POLICY
    except Exception as exc:
        print(f"[FAIL] Repository publication failed: {exc}")
        return EXIT_GIT

    print("[PASS] Repository publication completed.")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
