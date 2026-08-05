#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, re, sys, subprocess
from pathlib import Path
from typing import Any
import yaml
from jsonschema import Draft202012Validator, RefResolver

ROOT = Path(__file__).resolve().parents[2]
results: list[dict[str, Any]] = []
INTEGRITY_TEXT_SUFFIXES = {".py", ".yaml", ".yml", ".json", ".md", ".txt", ".bat"}
INTEGRITY_TEXT_NAMES = {"LICENSE", "requirements.txt"}

def integrity_digest(path: Path) -> str:
    if path.name in INTEGRITY_TEXT_NAMES or path.suffix.lower() in INTEGRITY_TEXT_SUFFIXES:
        text = path.read_text(encoding="utf-8")
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()

def result(cid: str, status: str, details: str) -> None:
    results.append({"id": cid, "status": status, "details": details})

parse_errors=[]; docs={}
for p in sorted(ROOT.rglob("*.yaml")):
    try: docs[str(p.relative_to(ROOT)).replace("\\", "/")]=yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as exc: parse_errors.append(f"{p.relative_to(ROOT)}: {exc}")
result("RV-001", "pass" if not parse_errors else "fail", "All YAML parsed" if not parse_errors else "; ".join(parse_errors))

manifest=docs.get("cerebro.yaml", {})
missing=[]
for section in ("runtime","core","standards"):
    for path in manifest.get(section,{}).values():
        if not (ROOT/path).exists(): missing.append(path)
source_declaration=manifest.get("source_authority",{}).get("declaration")
if source_declaration and not (ROOT/source_declaration).exists():
    missing.append(source_declaration)
for eng in manifest.get("engines",[]):
    p=ROOT/eng["path"]
    if not p.is_dir(): missing.append(eng["path"])
    if not (p/"module.yaml").exists(): missing.append(f'{eng["path"]}module.yaml')
result("RV-002", "pass" if not missing else "fail", "All manifest references exist" if not missing else f"Missing: {missing}")

schema_paths=["schemas/module-contract.schema.yaml","schemas/context-item.schema.yaml","schemas/trace-event.schema.yaml","schemas/runtime.schema.yaml"]
schemas=[docs[p] for p in schema_paths]
store={s.get("$id"):s for s in schemas if isinstance(s,dict) and s.get("$id")}
module_schema=docs["schemas/module-contract.schema.yaml"]
runtime_schema=docs["schemas/runtime.schema.yaml"]

contract_errors=[]
module_validator=Draft202012Validator(module_schema, resolver=RefResolver.from_schema(module_schema, store=store))
for eng in manifest.get("engines",[]):
    rel=f'{eng["path"]}module.yaml'
    data=docs.get(rel)
    if data is None: continue
    for err in module_validator.iter_errors(data): contract_errors.append(f"{rel}:{'/'.join(map(str,err.path))}:{err.message}")
    if data.get("module",{}).get("id") != eng.get("id"): contract_errors.append(f"{rel}: module id mismatch")
result("RV-003", "pass" if not contract_errors else "fail", "All module contracts valid" if not contract_errors else "; ".join(contract_errors))

fixture=docs.get("tests/fixtures/initial-runtime.yaml")
runtime_errors=[]
if fixture is None: runtime_errors.append("Missing initial runtime fixture")
else:
    rv=Draft202012Validator(runtime_schema, resolver=RefResolver.from_schema(runtime_schema, store=store))
    runtime_errors=[f"{'/'.join(map(str,e.path))}:{e.message}" for e in rv.iter_errors(fixture)]
result("RV-004", "pass" if not runtime_errors else "fail", "Initial runtime fixture valid" if not runtime_errors else "; ".join(runtime_errors))

activation=docs.get("runtime/activation.yaml",{})
registered={e.get("id") for e in manifest.get("engines",[])}
unknown=[]
for mod in activation.get("always",[]):
    if mod not in registered: unknown.append(mod)
for mode,mods in activation.get("by_work_mode",{}).items():
    for mod in mods:
        if mod not in registered: unknown.append(f"{mode}:{mod}")
result("RV-005", "pass" if not unknown else "fail", "Activation references registered modules" if not unknown else f"Unknown: {unknown}")

transitions=docs.get("engines/dialog/transitions.yaml",{}).get("transitions",{})
states=set(docs.get("core/terminology.yaml",{}).get("terms",{}).get("dialog_state",[]))
bad=[]
for src,dsts in transitions.items():
    if src not in states: bad.append(src)
    for dst in dsts:
        if dst not in states: bad.append(f"{src}->{dst}")
result("RV-006", "pass" if not bad else "fail", "Dialog transitions use registered states" if not bad else f"Invalid: {bad}")

errors=set(docs.get("runtime/error-codes.yaml",{}).get("errors",{}))
refs=[]
for rel in docs:
    if rel=="runtime/error-codes.yaml": continue
    refs.extend(re.findall(r"\bE\d{3}\b",(ROOT/rel).read_text(encoding="utf-8")))
unknown_errors=sorted(set(refs)-errors)
result("RV-007", "pass" if not unknown_errors else "fail", "All error references registered" if not unknown_errors else f"Unknown: {unknown_errors}")

scenarios=docs.get("tests/acceptance/scenarios.yaml",{}).get("scenarios",[])
ids={s.get("id") for s in scenarios}
expected={f"AC-{i:03d}" for i in range(1,11)}
missing_scenarios=sorted(expected-ids)
result("RV-008", "pass" if not missing_scenarios else "fail", f"{len(scenarios)} acceptance scenarios declared" if not missing_scenarios else f"Missing: {missing_scenarios}")

proc=subprocess.run([sys.executable,"-m","unittest","discover","-s","tests/acceptance","-p","test_*.py"],cwd=ROOT,text=True,capture_output=True)
test_ok=proc.returncode==0 and "Ran 10 tests" in (proc.stdout+proc.stderr)
result("RV-009","pass" if test_ok else "fail","10 executable acceptance tests passed" if test_ok else (proc.stdout+proc.stderr)[-2000:])

progress_proc=subprocess.run([sys.executable,"-m","unittest","discover","-s","tests/progress","-p","test_*.py"],cwd=ROOT,text=True,capture_output=True)
progress_ok=progress_proc.returncode==0 and "Ran 8 tests" in (progress_proc.stdout+progress_proc.stderr)
result("RV-015","pass" if progress_ok else "fail","8 operational progress scenarios passed" if progress_ok else (progress_proc.stdout+progress_proc.stderr)[-2000:])

try:
    sys.path.insert(0,str(ROOT))
    from cerebro_runtime import CerebroRuntime
    engine=CerebroRuntime(ROOT)
    task={"input":"Determinism replay","goal":"Stable result","recommendation":"Option A"}
    deterministic=engine.state_hash(engine.run(task))==engine.state_hash(engine.run(task))
    result("RV-010","pass" if deterministic else "fail","Replay hashes are equivalent" if deterministic else "Replay hashes differ")
except Exception as exc:
    result("RV-010","fail",f"Determinism replay failed: {exc}")

integrity_path=ROOT/"validation/integrity.sha256"
if integrity_path.exists():
    expected_hashes={}
    for line in integrity_path.read_text().splitlines():
        if not line.strip(): continue
        digest,rel=line.split("  ",1); expected_hashes[rel]=digest
    mismatches=[rel for rel,digest in expected_hashes.items() if not (ROOT/rel).exists() or integrity_digest(ROOT/rel)!=digest]
    result("RV-011","pass" if not mismatches else "fail","Integrity manifest verified" if not mismatches else f"Mismatch: {mismatches}")
else:
    result("RV-011","fail","Missing validation/integrity.sha256")

standards_proc=subprocess.run([sys.executable,str(ROOT/"tooling/standards/validate_standards.py")],cwd=ROOT,text=True,capture_output=True)
result("RV-012","pass" if standards_proc.returncode==0 else "fail","Standards registry and documents valid" if standards_proc.returncode==0 else (standards_proc.stdout+standards_proc.stderr)[-2000:])

repository_proc=subprocess.run([sys.executable,str(ROOT/"tooling/repository/check_repository.py")],cwd=ROOT,text=True,capture_output=True)
result("RV-013","pass" if repository_proc.returncode==0 else "fail","Repository integrity valid" if repository_proc.returncode==0 else (repository_proc.stdout+repository_proc.stderr)[-2000:])

source=manifest.get("source_authority",{})
source_registry=docs.get("standards/standards.yaml",{})
registered_source=any(
    item.get("id")=="STD-SOURCE" and item.get("path")=="standards/source-authority.yaml" and item.get("required") is True
    for item in source_registry.get("documents",[])
)
source_errors=[]
if source.get("identity")!="Cerebro Source 1.0": source_errors.append("identity")
if source.get("authority")!="sole": source_errors.append("authority")
if source.get("declaration")!="standards/source-authority.yaml": source_errors.append("declaration")
if source.get("source_folder_required") is not False: source_errors.append("source_folder_required")
if source.get("implementation_authoritative") is not False: source_errors.append("implementation_authoritative")
if not registered_source: source_errors.append("STD-SOURCE registration")
if (ROOT/"Source").exists() or (ROOT/"source").exists(): source_errors.append("forbidden Source folder")
result(
    "RV-014",
    "pass" if not source_errors else "fail",
    "Cerebro Source 1.0 is the sole registered authority"
    if not source_errors
    else f"Source authority errors: {source_errors}"
)

required={c["id"] for c in docs.get("validation/release-criteria.yaml",{}).get("criteria",[]) if c.get("required")}
failed=[r["id"] for r in results if r["id"] in required and r["status"]!="pass"]
report={"schema":"cerebro-validation-report/v0.1","artifact":"Cerebro-Release-0.1","result":"pass" if not failed else "fail","failed_required":failed,"checks":results}
(ROOT/"validation/validation-report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
print(json.dumps(report,indent=2))
sys.exit(0 if not failed else 1)
