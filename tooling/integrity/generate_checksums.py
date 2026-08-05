#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT_IMPORT = Path(__file__).resolve().parents[2]
if str(ROOT_IMPORT) not in sys.path:
    sys.path.insert(0, str(ROOT_IMPORT))
import hashlib
from pathlib import Path
from tooling.common.paths import ROOT, VALIDATION_DIR, GENERATED_RELATIVE_PATHS, GENERATED_TOP_LEVEL_DIRS

ALLOWED_SUFFIXES = {".py", ".yaml", ".yml", ".json", ".md", ".txt", ".bat"}
ALLOWED_NAMES = {"LICENSE", "requirements.txt"}


def integrity_digest(path: Path) -> str:
    if path.name in ALLOWED_NAMES or path.suffix.lower() in ALLOWED_SUFFIXES:
        text = path.read_text(encoding="utf-8")
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def included(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if rel in GENERATED_RELATIVE_PATHS:
        return False
    if any(part in GENERATED_TOP_LEVEL_DIRS for part in path.relative_to(ROOT).parts):
        return False
    return path.name in ALLOWED_NAMES or path.suffix.lower() in ALLOWED_SUFFIXES


def main() -> int:
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for path in sorted(p for p in ROOT.rglob("*") if p.is_file() and included(p)):
        digest = integrity_digest(path)
        lines.append(f"{digest}  {path.relative_to(ROOT).as_posix()}")
    target = VALIDATION_DIR / "integrity.sha256"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Generated {target.relative_to(ROOT)} with {len(lines)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
