from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

ROOT = Path(__file__).resolve().parents[1]


class RuntimeInputError(ValueError):
    """Raised when a required runtime input is invalid."""


@dataclass(frozen=True)
class WorkAssessment:
    dependent_steps: str = "none"
    continuity_required: str = "no"
    deliverable_count: str = "one"
    ambiguity_risk: str = "low"
    duration: str = "single_response"


class CerebroRuntime:
    """Minimal deterministic runtime for Cerebro 0.1.

    The runtime accepts explicit machine-readable task features. Free-form text is
    retained as task input, but does not silently override explicit features.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ROOT
        self.activation = self._load("runtime/activation.yaml")
        self.dialog_rules = self._load("engines/dialog/rules.yaml")
        self.initial = self._load("tests/fixtures/initial-runtime.yaml")

    def _load(self, relative: str) -> dict[str, Any]:
        return yaml.safe_load((self.root / relative).read_text(encoding="utf-8"))

    @staticmethod
    def _canonical(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def state_hash(cls, state: Mapping[str, Any]) -> str:
        comparable = copy.deepcopy(dict(state))
        comparable.get("runtime", {}).pop("session_id", None)
        comparable["trace"] = {"events": [
            {k: v for k, v in event.items() if k not in {"id", "metadata"}}
            for event in comparable.get("trace", {}).get("events", [])
        ]}
        return hashlib.sha256(cls._canonical(comparable).encode("utf-8")).hexdigest()

    def assess_mode(self, features: Mapping[str, str] | None = None) -> tuple[str, int]:
        features = dict(features or {})
        assessment = WorkAssessment(**{
            key: features.get(key, getattr(WorkAssessment(), key))
            for key in WorkAssessment.__dataclass_fields__
        })
        score = 0
        factors = self.dialog_rules["assessment_factors"]
        for key, value in assessment.__dict__.items():
            if value not in factors[key]:
                raise RuntimeInputError(f"Invalid assessment value: {key}={value}")
            score += int(factors[key][value])
        thresholds = self.dialog_rules["thresholds"]
        for mode in ("standard", "collaboration", "project"):
            bounds = thresholds[mode]
            if bounds["min"] <= score <= bounds["max"]:
                return mode, score
        raise RuntimeInputError(f"Assessment score outside configured thresholds: {score}")

    def _modules_for(self, mode: str) -> list[str]:
        modules = list(self.activation.get("always", []))
        modules.extend(self.activation.get("by_work_mode", {}).get(mode, []))
        return list(dict.fromkeys(modules))

    @staticmethod
    def _context_item(index: int, item_type: str, value: Any, source: str,
                      authority: int, status: str = "active",
                      derived_from: list[str] | None = None) -> dict[str, Any]:
        return {
            "id": f"ctx-{index:04d}",
            "type": item_type,
            "value": value,
            "status": status,
            "authority_level": authority,
            "source": {"type": source, "reference": None, "verified": source == "user"},
            "relations": {
                "derived_from": derived_from or [], "supports": [],
                "conflicts_with": [], "supersedes": []
            },
            "activation": None,
            "metadata": {"created_at": None, "updated_at": None, "tags": []},
        }

    def run(self, task: Mapping[str, Any] | str, *,
            features: Mapping[str, str] | None = None,
            presentation_model: str | None = None) -> dict[str, Any]:
        payload = {"input": task} if isinstance(task, str) else dict(task)
        if "input" not in payload:
            raise RuntimeInputError("task.input is required")

        state = copy.deepcopy(self.initial)
        state["runtime"].update({"status": "active", "session_id": None})
        state["task"].update({
            "id": payload.get("id", "task-runtime"),
            "input": payload["input"],
            "goal": payload.get("goal"),
            "scope": payload.get("scope"),
            "constraints": payload.get("constraints", []),
            "expected_outputs": payload.get("expected_outputs", []),
        })

        mode, score = self.assess_mode(features or payload.get("features"))
        state["dialog"]["work_mode"] = mode
        state["dialog"]["active_modules"] = self._modules_for(mode)
        state["dialog"]["state"] = "analysis"
        state["project"]["active"] = mode == "project"
        state["project"]["phase"] = "startup" if mode == "project" else None
        state["project"]["deliverables"] = payload.get("deliverables", [])

        context_items: list[dict[str, Any]] = []
        for raw in payload.get("context", []):
            context_items.append(copy.deepcopy(raw))

        recommendation = payload.get("recommendation")
        if recommendation is not None:
            context_items.append(self._context_item(
                len(context_items) + 1, "recommendation", recommendation,
                "assistant_inference", 3,
                derived_from=payload.get("recommendation_basis", ["task.input"]),
            ))

        approved = bool(payload.get("approve_recommendation", False))
        if approved:
            recs = [x for x in context_items if x.get("type") == "recommendation"]
            if not recs:
                raise RuntimeInputError("Approval requires a recommendation")
            rec = recs[-1]
            decision = self._context_item(
                len(context_items) + 1, "decision", rec["value"], "user", 4,
                derived_from=[rec["id"]],
            )
            decision["activation"] = {"activated_by": "user", "activation_reference": rec["id"]}
            context_items.append(decision)

        decisions = [x for x in context_items if x.get("type") == "decision" and x.get("status") == "active"]
        decision_values: dict[str, list[dict[str, Any]]] = {}
        for item in decisions:
            key = str(item.get("value", {}).get("key")) if isinstance(item.get("value"), dict) else "default"
            decision_values.setdefault(key, []).append(item)
        conflicts = [items for items in decision_values.values()
                     if len({self._canonical(i.get("value")) for i in items}) > 1]

        state["context"]["items"] = context_items
        warnings: list[str] = []
        if payload.get("missing_noncritical_detail"):
            assumption = self._context_item(
                len(context_items) + 1, "assumption",
                payload.get("assumption", "unspecified non-critical detail"),
                "assistant_inference", 2,
            )
            state["context"]["items"].append(assumption)
            warnings.append("noncritical_detail_assumed")

        goal_required = bool(payload.get("goal_required", mode == "project"))
        if conflicts:
            ids = [i["id"] for group in conflicts for i in group]
            for group in conflicts:
                for item in group:
                    item["relations"]["conflicts_with"] = [x["id"] for x in group if x["id"] != item["id"]]
            self._block(state, "conflicting_decisions", ids, "user_decision", "resolve_conflict")
        elif goal_required and not state["task"]["goal"]:
            self._block(state, "missing_required_goal", ["task.goal"], "user_information", "define_goal")
        else:
            state["dialog"]["state"] = "verification"
            model = presentation_model or payload.get("presentation_model") or (
                "system_format" if mode in {"collaboration", "project"} else "text"
            )
            state["presentation"].update({
                "model": model,
                "detail_level": payload.get("detail_level", "standard"),
                "status_visible": mode != "standard",
            })
            state["quality"]["status"] = "warning" if warnings else "pass"
            state["quality"]["checks"] = [
                {"id": "QG-INPUT", "status": "pass", "rule_refs": [], "evidence_refs": ["task.input"]},
                {"id": "QG-ORCHESTRATION", "status": "pass", "rule_refs": [], "evidence_refs": ["dialog.work_mode"]},
                {"id": "QG-CONTEXT", "status": "warning" if warnings else "pass", "rule_refs": [], "evidence_refs": []},
                {"id": "QG-DELIVERY", "status": "pass", "rule_refs": [], "evidence_refs": ["presentation.model"]},
            ]
            state["quality"]["issues"] = [
                {"id": f"issue-{i+1}", "severity": "warning", "code": code,
                 "message_key": code, "related_refs": []}
                for i, code in enumerate(warnings)
            ]
            state["dialog"]["state"] = "finalization"
            state["runtime"]["status"] = "completed"

        state["trace"]["events"] = self._trace(state, score)
        return state

    @staticmethod
    def _block(state: dict[str, Any], reason: str, fields: list[str], input_type: str, prompt: str) -> None:
        state["runtime"]["status"] = "blocked"
        state["dialog"]["state"] = "clarification"
        state["dialog"]["clarification_required"] = True
        state["dialog"]["control_stop"] = {
            "id": "stop-0001", "reason_code": reason,
            "blocking_fields": fields,
            "requested_input": {"type": input_type, "prompt_key": prompt},
        }
        state["quality"]["status"] = "fail"
        state["quality"]["checks"] = []
        state["quality"]["issues"] = [{
            "id": "issue-1", "severity": "critical", "code": reason,
            "message_key": reason, "related_refs": fields,
        }]

    @staticmethod
    def _trace(state: dict[str, Any], score: int) -> list[dict[str, Any]]:
        events = [
            ("runtime_initialized", "runtime", ["task.input"], ["runtime.status"], "success"),
            ("work_mode_selected", "dialog", ["task.input"], ["dialog.work_mode"], "success"),
            ("module_activated", "runtime", ["dialog.work_mode"], ["dialog.active_modules"], "success"),
        ]
        if state["dialog"]["control_stop"]:
            events.append(("control_stop_created", "dialog", ["context.items"], ["dialog.control_stop"], "failed"))
        else:
            events.extend([
                ("quality_check_completed", "quality-lite", ["runtime"], ["quality.status"], "success"),
                ("presentation_selected", "presentation-lite", ["runtime"], ["presentation.model"], "success"),
                ("runtime_completed", "runtime", ["quality.status"], ["runtime.status"], "success"),
            ])
        return [{
            "id": f"evt-{i:04d}", "sequence": i, "type": typ, "actor": actor,
            "input_refs": inputs, "output_refs": outputs,
            "rule_refs": [f"score:{score}"] if typ == "work_mode_selected" else [],
            "result": result, "metadata": {"timestamp": None, "message_key": None},
        } for i, (typ, actor, inputs, outputs, result) in enumerate(events, start=1)]
