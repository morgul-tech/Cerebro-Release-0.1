#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT_IMPORT = Path(__file__).resolve().parents[2]
if str(ROOT_IMPORT) not in sys.path:
    sys.path.insert(0, str(ROOT_IMPORT))
import json
from tooling.common.paths import ROOT, VALIDATION_DIR, REPORTS_DIR


def main() -> int:
    source = VALIDATION_DIR / "validation-report.json"
    if not source.exists():
        print("Missing validation/validation-report.json. Run validation first.")
        return 1
    data = json.loads(source.read_text(encoding="utf-8"))
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "CEREBRO RELEASE VALIDATION REPORT",
        "=" * 36,
        f"Artifact: {data.get('artifact')}",
        f"Result: {str(data.get('result', 'unknown')).upper()}",
        "",
    ]
    for check in data.get("checks", []):
        lines.append(f"[{str(check.get('status', '')).upper():7}] {check.get('id')}: {check.get('details', '')}")
    failed = data.get("failed_required", [])
    lines.extend(["", f"Failed required checks: {', '.join(failed) if failed else 'None'}"])
    target = REPORTS_DIR / "validation-report.txt"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Generated {target.relative_to(ROOT)}")
    return 0 if data.get("result") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
