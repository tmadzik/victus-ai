"""Model cards — a structured, honest record shipped with every model artifact.

A model card states intended use, the data it was trained/evaluated on, headline
metrics (discrimination + calibration), and — crucially for a clinical
decision-support tool — its limitations and the populations on which it has NOT
been validated. ``render_markdown`` emits a reviewer-readable card; pair it with
the existing ``*.pt.meta.json`` artifact metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ModelCard:
    name: str
    version: str
    intended_use: str
    not_intended_use: str
    training_data: str
    evaluation_data: str
    # Free-form metric blocks, e.g. {"diabetes": {"roc_auc": 0.74, "ece": 0.05}}.
    metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    ethical_considerations: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

    def render_markdown(self) -> str:
        lines: list[str] = [
            f"# Model Card — {self.name} ({self.version})",
            "",
            "## Intended use",
            self.intended_use,
            "",
            "## Not intended for",
            self.not_intended_use,
            "",
            "## Training data",
            self.training_data,
            "",
            "## Evaluation data",
            self.evaluation_data,
            "",
            "## Metrics",
        ]
        if self.metrics:
            for group, block in self.metrics.items():
                metric_str = ", ".join(
                    f"{k} = {v:.3f}" for k, v in block.items()
                )
                lines.append(f"- **{group}**: {metric_str}")
        else:
            lines.append("- _none reported_")

        for heading, items in (
            ("Limitations", self.limitations),
            ("Ethical considerations", self.ethical_considerations),
            ("Caveats & recommendations", self.caveats),
        ):
            lines += ["", f"## {heading}"]
            lines += [f"- {item}" for item in items] or ["- _none_"]

        return "\n".join(lines) + "\n"


def triage_model_card(
    *, version: str, metrics: dict[str, dict[str, float]]
) -> ModelCard:
    """A pre-filled card for the 3B-Triage model with the standing caveats."""
    return ModelCard(
        name="Victus 3B-Triage (Dirichlet-EDL, DANN)",
        version=version,
        intended_use=(
            "Non-diagnostic NCD screening (obesity, hypertension, diabetes) from "
            "tape-measure anthropometry + a symptom audit, surfacing a "
            "GREEN/YELLOW/RED state with explicit uncertainty for triage."
        ),
        not_intended_use=(
            "Not a diagnosis, not a substitute for clinical measurement or "
            "laboratory testing, and not validated for incident-risk prediction "
            "(the training data is cross-sectional → prevalent-case detection)."
        ),
        training_data=(
            "Clinician-labelled research_triage_cases (Victus NCD field study, "
            "SA + NG) with ground-truth labels: BMI≥30, BP≥140/90, HbA1c≥6.5%/"
            "FPG≥7.0. Predictive-task contracts (triage/tasks.py) exclude each "
            "label's defining measurement from its head to prevent leakage."
        ),
        evaluation_data=(
            "Site- and country-held-out splits (group_holdout_split). External / "
            "prospective kiosk-population validation pending."
        ),
        metrics=metrics,
        limitations=[
            "Facility-recruited training population differs from the kiosk "
            "walk-up deployment population — recalibration expected.",
            "Diabetes is the only genuine proxy task; obesity/hypertension are "
            "deterministic when their defining measurement is present.",
            "Subgroup power (Fitzpatrick, urban/rural, sex) is limited at current N.",
        ],
        ethical_considerations=[
            "Decision-support only; a RED state escalates to a clinician.",
            "Deterministic safety overrides bypass the model for red-flag symptoms.",
        ],
        caveats=[
            "Report calibration (ECE, reliability) alongside ROC-AUC.",
            "Re-validate per site before each new deployment.",
        ],
    )
