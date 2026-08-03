from __future__ import annotations
import argparse, json
from pathlib import Path
import yaml
from .runtime import CerebroRuntime

parser = argparse.ArgumentParser(description="Run Cerebro 0.1 minimal runtime")
parser.add_argument("task", help="YAML/JSON task file")
args = parser.parse_args()
path = Path(args.task)
data = yaml.safe_load(path.read_text(encoding="utf-8"))
print(json.dumps(CerebroRuntime().run(data), ensure_ascii=False, indent=2, sort_keys=True))
