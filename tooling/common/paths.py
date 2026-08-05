from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALIDATION_DIR = ROOT / "validation"
REPORTS_DIR = ROOT / "reports"
BUILDS_DIR = ROOT / "builds"

GENERATED_RELATIVE_PATHS = {
    "validation/integrity.sha256",
    "validation/validation-report.json",
    "validation/repository-report.json",
    "validation/repository-report.txt",
    "validation/standards-report.json",
    "reports/validation-report.txt",
}
GENERATED_TOP_LEVEL_DIRS = {"builds", ".git", "__pycache__", ".pytest_cache"}
