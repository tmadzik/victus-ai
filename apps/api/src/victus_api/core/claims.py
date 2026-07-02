"""Clinical-claims gate — the enforced precondition between "the model runs" and
"the model is allowed to speak to a patient".

A model-derived NCD risk state (RED/YELLOW/GREEN) is a *clinical claim*. Until
the model has passed prospective validation on the deployed population
(docs/PROSPECTIVE_VALIDATION_PLAN.md), the platform must not present that state
as something a person should act on. This module resolves which mode a
deployment is in and supplies the patient-facing copy for each; the service
layer applies it at the single response chokepoint.

Design notes:
* Default is ``RESEARCH_DEMONSTRATOR`` — the honest, safe default. Clinical
  claims require an explicit opt-in *and* a named validated model card
  (``Settings.clinical_claims_active``); enabling the flag alone is not enough.
* Deterministic red-flag safety guidance is **not** a model claim — it is
  conservative first-aid triage from reported symptoms (e.g. crushing chest
  pain). It is preserved in every mode; withholding it would be less safe.
* This module is schema-free (no dependency on any domain's response type) so it
  can be reused by Pathway A, Pathway B, and the delivery surfaces without an
  import cycle.
"""

from __future__ import annotations

import enum

from victus_api.config import Settings


class ClaimsMode(str, enum.Enum):
    """Whether the deployment may present model outputs as clinical results."""

    CLINICAL = "CLINICAL"
    RESEARCH_DEMONSTRATOR = "RESEARCH_DEMONSTRATOR"


def resolve_claims_mode(settings: Settings) -> ClaimsMode:
    """The gate: CLINICAL only when explicitly enabled with a validated model
    card, else RESEARCH_DEMONSTRATOR."""
    return (
        ClaimsMode.CLINICAL
        if settings.clinical_claims_active
        else ClaimsMode.RESEARCH_DEMONSTRATOR
    )


# Patient-facing disclaimer shown with every assessment.
CLINICAL_DISCLAIMER = (
    "This is a wellness screening, not a diagnosis. Discuss these results with a "
    "clinician; if you feel unwell, seek care now."
)
RESEARCH_DISCLAIMER = (
    "⚠️ Research demonstrator — NOT a medical device and NOT a clinical result. "
    "These outputs have not been clinically validated for this population and "
    "must not be used to make any health decision."
)

# The de-claimed replacement for a model-derived "next action" when the gate is
# closed. Note it does not tell the person to act on the risk state.
RESEARCH_NEXT_ACTION = (
    "No action is implied by this research demonstrator. The result above is an "
    "unvalidated model output shown for demonstration only."
)
RESEARCH_PER_DISEASE_ACTION = "Unvalidated demonstrator output — not clinical advice."


def disclaimer_for(mode: ClaimsMode) -> str:
    return (
        CLINICAL_DISCLAIMER
        if mode is ClaimsMode.CLINICAL
        else RESEARCH_DISCLAIMER
    )
