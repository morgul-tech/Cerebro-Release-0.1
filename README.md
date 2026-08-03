# Cerebro Release 0.1

Cerebro Release 0.1 is the first minimal operational release of the Cerebro collaboration runtime.

## Purpose

Provide a deterministic, machine-first framework for structured conversations and larger projects without adding unnecessary process to simple dialogue.

## Core capabilities

- work-mode selection: `standard`, `collaboration`, `project`
- explicit runtime state
- controlled context and authority transitions
- deterministic module activation
- project-lite coordination
- quality gates
- presentation as the final rendering step

## Runtime pipeline

```text
Input
→ Normalize
→ Classify
→ Assess work mode
→ Activate modules
→ Transform runtime state
→ Validate context and conflicts
→ Run quality gates
→ Select presentation
→ Render output
```

## Design principles

- machine first
- deterministic internal logic
- one responsibility per module
- single source of truth
- explicit state
- traceable outcomes
- low coupling
- configuration over hardcoding
- replaceable modules
- shared data model
- structured engine output
- presentation last
- generated status
- composability
- minimal release scope
- policy over procedure
- fail explicitly
- no implicit promotion

## Status

Release candidate for Cerebro 0.1.0.


## Minimal runtime

Run the executable acceptance suite:

```bash
python run_tests.py
```

Run a machine-readable task:

```bash
python -m cerebro_runtime path/to/task.yaml
```

The runtime is intentionally minimal and deterministic. Work-mode classification is driven by explicit task features and the configured scoring model.

## Local tooling

All tooling runs locally. Python is a replaceable reference implementation and support tool; Cerebro's authoritative rules remain in the machine-readable YAML and schema files.

Double-click the Windows launchers in `scripts/`, or use the shared command line entry point:

```bash
python cerebro_tool.py test
python cerebro_tool.py validate
python cerebro_tool.py report
python cerebro_tool.py checksum
python cerebro_tool.py zip
python cerebro_tool.py build
```

`build` runs tests, regenerates checksums, validates the release, creates a human-readable report, and packages a ZIP.
