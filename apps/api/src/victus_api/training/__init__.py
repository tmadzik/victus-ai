"""Training pipeline for the Pathway A Evidential Deep Learning classifier.

This package is intentionally separated from runtime concerns: it is only
required when ``uv sync --extra ml`` has been run. The artefacts it produces —
a state-dict checkpoint and a ``.meta.json`` sidecar — are consumed by
:class:`victus_api.triage.edl.inference.EvidentialTorchModel` at runtime.
"""
