#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, shutil, subprocess, sys, zipfile
from pathlib import Path
from typing import Any
import yaml

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "tooling/patch/install_patch.py"
LOCATOR = ROOT / "tooling/patch/locate_cerebro.py"
VALIDATOR = ROOT / "tooling/patch/validate_patch.py"
BUILDS = ROOT / "builds" / "patches"
EXIT_BUILD = 6

def sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes())
    return digest.hexdigest()

def load_plan(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    missing = [k for k in ("id", "name", "target", "files") if k not in data]
    if missing:
        raise ValueError(f"Missing fields: {missing}")
    return data

def bat_content(patch_id: str) -> str:
    lines = [
        "@echo off", "setlocal", "",
        f"title Cerebro - Install Patch {patch_id}", "",
        'set "PYTHON_CMD="',
        "where py >nul 2>nul",
        "if %errorlevel%==0 (",
        '    set "PYTHON_CMD=py"',
        ") else (",
        "    where python >nul 2>nul",
        "    if %errorlevel%==0 (",
        '        set "PYTHON_CMD=python"',
        "    )",
        ")",
        "",
        "if not defined PYTHON_CMD (",
        "    echo.", "    echo [FAIL] Python was not found.",
        "    pause", "    endlocal", "    exit /b 3", ")",
        "",
        'pushd "%~dp0"',
        '%PYTHON_CMD% "installer\\patch_installer.py"',
        'set "RESULT=%errorlevel%"',
        "popd", "",
        'if "%RESULT%"=="0" (',
        f"    echo [PASS] Patch {patch_id} installed successfully.",
        ") else (",
        f"    echo [FAIL] Patch {patch_id} installation failed with exit code %RESULT%.",
        ")",
        "echo.", "pause", "endlocal & exit /b %RESULT%",
    ]
    return "\r\n".join(lines) + "\r\n"

def build(plan_path: Path) -> Path:
    plan = load_plan(plan_path)
    patch_id = str(plan["id"])
    safe_name = str(plan["name"]).replace(" ", "-")
    package_name = f"Cerebro-Patch-{patch_id}-{safe_name}"
    work = BUILDS / package_name
    if work.exists():
        shutil.rmtree(work)
    (work / "repo").mkdir(parents=True)
    (work / "installer").mkdir(parents=True)

    shutil.copy2(INSTALLER, work / "installer/patch_installer.py")
    shutil.copy2(LOCATOR, work / "installer/locate_cerebro.py")
    (work / "INSTALL_PATCH.bat").write_text(bat_content(patch_id), encoding="ascii")

    manifest_files = []
    for item in plan["files"]:
        source_rel = str(item["source"]).replace("\\", "/")
        source = ROOT / source_rel
        if not source.is_file():
            raise FileNotFoundError(source_rel)
        payload = work / "repo" / source_rel
        payload.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, payload)
        manifest_files.append({
            "source": f"repo/{source_rel}",
            "destination": item.get("destination", f"{{REPOSITORY_ROOT}}/{source_rel}"),
            "operation": item.get("operation", "replace"),
            "sha256": sha256(payload),
        })

    manifest = {
        "schema": "cerebro-patch-manifest/v0.1",
        "patch": {
            "id": patch_id,
            "name": plan["name"],
            "target": plan["target"],
            "prerequisite": plan.get("prerequisite", []),
        },
        "files": manifest_files,
        "verification": plan.get("verification", [
            ["{PYTHON}", "cerebro_tool.py", "repository"],
            ["{PYTHON}", "cerebro_tool.py", "checksum"],
            ["{PYTHON}", "cerebro_tool.py", "validate"],
        ]),
    }
    (work / "PATCH_MANIFEST.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
    )

    install_lines = [
        "CEREBRO PATCH INSTALLATION", "===========================", "",
        f"PATCH ID: {patch_id}", f"PATCH NAME: {plan['name']}", "",
        "AUTOMATIC INSTALLATION", "======================", "",
        "Extract the ZIP and double-click INSTALL_PATCH.bat.", "",
        "PAYLOAD FILES", "=============", "",
    ]
    for item in manifest_files:
        install_lines.append(
            f"- {item['source']} -> {item['destination']} ({item['operation'].upper()})"
        )
    (work / "PATCH_INSTALL.txt").write_text("\n".join(install_lines) + "\n", encoding="utf-8")

    change_lines = [
        "CEREBRO PATCH CHANGELOG", "========================", "",
        f"PATCH ID: {patch_id}", f"PATCH NAME: {plan['name']}", "",
    ]
    for heading in ("added", "changed", "fixed", "removed", "unchanged"):
        change_lines.append(heading.upper() + ":")
        values = plan.get("changelog", {}).get(heading, [])
        change_lines.extend(f"- {v}" for v in values)
        if not values:
            change_lines.append("- None")
        change_lines.append("")
    (work / "PATCH_CHANGELOG.txt").write_text("\n".join(change_lines), encoding="utf-8")

    if subprocess.run([sys.executable, str(VALIDATOR), str(work)], cwd=ROOT).returncode != 0:
        raise RuntimeError("Directory validation failed.")

    BUILDS.mkdir(parents=True, exist_ok=True)
    target = BUILDS / f"{package_name}.zip"
    if target.exists():
        target.unlink()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(work.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(work))

    if subprocess.run([sys.executable, str(VALIDATOR), str(target)], cwd=ROOT).returncode != 0:
        target.unlink(missing_ok=True)
        raise RuntimeError("ZIP validation failed.")
    return target

def main() -> int:
    parser = argparse.ArgumentParser(description="Build a validated Cerebro patch")
    parser.add_argument("plan")
    args = parser.parse_args()
    try:
        target = build(Path(args.plan).resolve())
    except Exception as exc:
        print(f"[FAIL] Patch build failed: {exc}")
        return EXIT_BUILD
    print(f"[PASS] Created validated patch: {target}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
