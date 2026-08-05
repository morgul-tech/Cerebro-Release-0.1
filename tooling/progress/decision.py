from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Outcome(str, Enum):
    CONTINUE = "CONTINUE"
    REMEDIATE_AND_CONTINUE = "REMEDIATE_AND_CONTINUE"
    RETRY = "RETRY"
    USER_DECISION_REQUIRED = "USER_DECISION_REQUIRED"
    SAFETY_BLOCK = "SAFETY_BLOCK"


@dataclass(frozen=True)
class DecisionContext:
    active_authorized_objective: bool
    safety_block: bool = False
    missing_authority: bool = False
    genuine_user_choice: bool = False
    qualified_remediation: bool = False
    retry_requested: bool = False
    progress_delta: bool = False


def decide(context: DecisionContext) -> Outcome:
    if context.safety_block:
        return Outcome.SAFETY_BLOCK
    if not context.active_authorized_objective or context.missing_authority:
        return Outcome.USER_DECISION_REQUIRED
    if context.genuine_user_choice:
        return Outcome.USER_DECISION_REQUIRED
    if context.qualified_remediation:
        return Outcome.REMEDIATE_AND_CONTINUE
    if context.retry_requested:
        return Outcome.RETRY if context.progress_delta else Outcome.SAFETY_BLOCK
    return Outcome.CONTINUE

