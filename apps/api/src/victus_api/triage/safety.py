"""Deterministic clinical-safety overrides for Pathway A.

These rules are evaluated BEFORE the EDL model is ever invoked. Any matched
trigger short-circuits the entire pipeline to a RED clinical-referral state
with a human-legible reason set — the neural network does not get a vote.

Source: Victus AI clinical-safety brief; all symptoms in
``SAFETY_OVERRIDE_SYMPTOM_KEYS`` are well-established red-flag presentations
for advanced NCDs (DM hyperglycaemic crisis, acute cardiovascular events,
hypertensive emergency).

Defence in depth: the web client *also* short-circuits to RED locally so the
user sees the referral instantly even before the network call resolves. The
API result is authoritative for the audit log.
"""

from __future__ import annotations

from dataclasses import dataclass

from victus_api.triage.schemas import SAFETY_OVERRIDE_SYMPTOM_KEYS, SymptomAudit


@dataclass(frozen=True, slots=True)
class SafetyDecision:
    triggered: bool
    reasons: tuple[str, ...]


def evaluate_safety_overrides(symptoms: SymptomAudit) -> SafetyDecision:
    """Return the set of safety triggers reported by the user.

    Unknown / out-of-vocabulary symptom keys are silently dropped — the
    Pydantic layer above already rejects malformed payloads.
    """
    matched = tuple(
        sorted(
            key
            for key in symptoms.safety_triggers
            if key in SAFETY_OVERRIDE_SYMPTOM_KEYS
        )
    )
    return SafetyDecision(triggered=bool(matched), reasons=matched)
