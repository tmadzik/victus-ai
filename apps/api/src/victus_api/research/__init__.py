"""Research console — labelled training-data capture for the two models.

Pathway A (triage EDL): clinician/CHW-entered, ground-truth-labelled cases
(``research_triage_cases``) where obesity/hypertension are objective (measured
BMI/BP) and diabetes is anchored on HbA1c / fasting glucose — exported to
retrain the multi-head DANN-EDL on recruited data instead of dataset proxies.

Pathway B (TOI/rPPG): the existing calibration + study domains already capture
rPPG-vs-reference pairs; the console surfaces them alongside this corpus.
"""
