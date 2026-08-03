#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, re, sys, subprocess
from pathlib import Path
from typing import Any
import yaml
from jsonschema import Draft202012Validator, RefResolver

ROOT = Path(__file__).resolve().parents[2]
results: list[dict[str, Any]] = []

def result(cid: str, status: str, details: str) -> None:
    results.append({"id": cid, "status": status, "details": details})

def load(path: str) -> Any:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))

# RV-001
parse_errors=[]
docs={}
for p in sorted(ROOT.rglob("*.yaml")):
    try: docs[str(p.relative_to(ROOT))]=yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as exc: parse_errors.append(f"{p.relative_to(ROOT)}: {exc}")
result("RV-001", "pass" if not parse_errors else "fail", "All YAML parsed" if not parse_errors else "; ".join(parse_errors))

manifest=docs.get("cerebro.yaml", {})
# RV-002
missing=[]
for section in ("runtime","core"):
    for path in manifest.get(section,{}).values():
        if not (ROOT/path).exists(): missing.append(path)
for eng in manifest.get("engines",[]):
    p=ROOT/eng["path"]
    if not p.is_dir(): missing.append(eng["path"])
    if not (p/"module.yaml").exists(): missing.append(f'{eng["path"]}module.yaml')
result("RV-002", "pass" if not missing else "fail", "All manifest references exist" if not missing else f"Missing: {missing}")

# Schema validation setup
schema_paths=["schemas/module-contract.schema.yaml","schemas/context-item.schema.yaml","schemas/trace-event.schema.yaml","schemas/runtime.schema.yaml"]
schemas=[docs[p] for p in schema_paths]
store={s.get("$id"):s for s in schemas if isinstance(s,dict) and s.get("$id")}
module_schema=docs["schemas/module-contract.schema.yaml"]
runtime_schema=docs["schemas/runtime.schema.yaml"]

# RV-003
contract_errors=[]
validator=Draft202012Validator(module_schema, resolver=RefResolver.from_schema(module_schema, store=store))
for eng in manifest.get("engines",[]):
    rel=f'{eng["path"]}module.yaml'
    data=docs.get(rel)
    if data is None: continue
    for err in validator.iter_errors(data): contract_errors.append(f"{rel}:{'/'.join(map(str,err.path))}:{err.message}")
    if data.get("module",{}).get("id") != eng.get("id"): contract_errors.append(f"{rel}: module id mismatch")
result("RV-003", "pass" if not contract_errors else "fail", "All module contracts valid" if not contract_errors else "; ".join(contract_errors))

# RV-004
fixture=docs.get("tests/fixtures/initial-runtime.yaml")
runtime_errors=[]
if fixture is None: runtime_errors.append("Missing initial runtime fixture")
else:
    rv=Draft202012Validator(runtime_schema, resolver=RefResolver.from_schema(runtime_schema, store=store))
    runtime_errors=[f"{'/'.join(map(str,e.path))}:{e.message}" for e in rv.iter_errors(fixture)]
result("RV-004", "pass" if not runtime_errors else "fail", "Initial runtime fixture valid" if not runtime_errors else "; ".join(runtime_errors))

# RV-005
activation=docs.get("runtime/activation.yaml",{})
registered={e.get("id") for e in manifest.get("engines",[])}
unknown=[]
for mod in activation.get("always",[]):
    if mod not in registered: unknown.append(mod)
for mode,mods in activation.get("by_work_mode",{}).items():
    for mod in mods:
        if mod not in registered: unknown.append(f"{mode}:{mod}")
result("RV-005", "pass" if not unknown else "fail", "Activation references registered modules" if not unknown else f"Unknown: {unknown}")

# RV-006
transitions=docs.get("engines/dialog/transitions.yaml",{}).get("transitions",{})
states=set(docs.get("core/terminology.yaml",{}).get("terms",{}).get("dialog_state",[]))
bad=[]
for src,dsts in transitions.items():
    if src not in states: bad.append(src)
    for dst in dsts:
        if dst not in states: bad.append(f"{src}->{dst}")
result("RV-006", "pass" if not bad else "fail", "Dialog transitions use registered states" if not bad else f"Invalid: {bad}")

# RV-007
errors=set(docs.get("runtime/error-codes.yaml",{}).get("errors",{}))
refs=[]
for rel,data in docs.items():
    if rel=="runtime/error-codes.yaml": continue
    text=(ROOT/rel).read_text(encoding="utf-8")
    refs.extend(re.findall(r"\bE\d{3}\b",text))
unknown_errors=sorted(set(refs)-errors)
result("RV-007", "pass" if not unknown_errors else "fail", "All error references registered" if not unknown_errors else f"Unknown: {unknown_errors}")

# RV-008
scenarios=docs.get("tests/acceptance/scenarios.yaml",{}).get("scenarios",[])
ids={s.get("id") for s in scenarios}
expected={f"AC-{i:03d}" for i in range(1,11)}
missing_scenarios=sorted(expected-ids)
result("RV-008", "pass" if not missing_scenarios else "fail", f"{len(scenarios)} acceptance scenarios declared" if not missing_scenarios else f"Missing: {missing_scenarios}")

# RV-009 executable acceptance tests
executables=list((ROOT/"tests").rglob("test_*.py")) + list((ROOT/"tests").rglob("*.spec.*"))
if executables:
    proc=subprocess.run([sys.executable, "run_tests.py"], cwd=ROOT, text=True, capture_output=True)
    test_ok=proc.returncode == 0 and "Ran 10 tests" in (proc.stdout + proc.stderr)
    result("RV-009", "pass" if test_ok else "fail", "10 executable acceptance tests passed" if test_ok else (proc.stdout + proc.stderr)[-2000:])
else:
    result("RV-009", "fail", "Acceptance scenarios are declarative only")

# RV-010 replay-based determinism
try:
    sys.path.insert(0, str(ROOT))
    from cerebro_runtime import CerebroRuntime
    engine=CerebroRuntime(ROOT)
    replay_task={"input":"Determinism replay","goal":"Stable result","recommendation":"Option A"}
    first=engine.run(replay_task)
    second=engine.run(replay_task)
    deterministic=engine.state_hash(first) == engine.state_hash(second)
    result("RV-010", "pass" if deterministic else "fail", "Replay hashes are equivalent" if deterministic else "Replay hashes differ")
except Exception as exc:
    result("RV-010", "fail", f"Determinism replay failed: {exc}")

# RV-011 integrity manifest
integrity_path=ROOT/"validation/integrity.sha256"
if integrity_path.exists():
    expected_hashes={}
    for line in integrity_path.read_text().splitlines():
        if not line.strip(): continue
        digest,rel=line.split("  ",1); expected_hashes[rel]=digest
    mismatches=[]
    for rel,digest in expected_hashes.items():
        p=ROOT/rel
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest: mismatches.append(rel)
    status="pass" if not mismatches else "fail"
    details="Integrity manifest verified" if not mismatches else f"Mismatch: {mismatches}"
else:
    status="fail"; details="Missing validation/integrity.sha256"
result("RV-011",status,details)

required={c["id"] for c in docs.get("validation/release-criteria.yaml",{}).get("criteria",[]) if c.get("required")}
failed=[r["id"] for r in results if r["id"] in required and r["status"]!="pass"]
report={"schema":"cerebro-validation-report/v0.1","artifact":"Cerebro-Release-0.1","result":"pass" if not failed else "fail","failed_required":failed,"checks":results}
(ROOT/"validation/validation-report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
print(json.dumps(report,indent=2))
sys.exit(0 if not failed else 1)
