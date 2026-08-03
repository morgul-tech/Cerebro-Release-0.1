#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT_IMPORT = Path(__file__).resolve().parents[2]
if str(ROOT_IMPORT) not in sys.path:
    sys.path.insert(0, str(ROOT_IMPORT))
import zipfile
from pathlib import Path
import yaml
from tooling.common.paths import ROOT, BUILDS_DIR, GENERATED_TOP_LEVEL_DIRS

EXCLUDE_PARTS = {".git", "__pycache__", ".pytest_cache", "builds"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}


def main() -> int:
    manifest = yaml.safe_load((ROOT / "cerebro.yaml").read_text(encoding="utf-8"))
    version = manifest["release"]["version"]
    status = manifest["release"]["status"]
    suffix = "RC" if status == "release-candidate" else status.replace("_", "-")
    BUILDS_DIR.mkdir(parents=True, exist_ok=True)
    target = BUILDS_DIR / f"Cerebro-Release-{version}-{suffix}.zip"
    root_name = f"Cerebro-Release-{version}"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(p for p in ROOT.rglob("*") if p.is_file()):
            rel = path.relative_to(ROOT)
            if any(part in EXCLUDE_PARTS for part in rel.parts) or path.suffix in EXCLUDE_SUFFIXES:
                continue
            archive.write(path, Path(root_name) / rel)
    print(f"Created {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
