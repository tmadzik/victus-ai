"""Front-of-platform participant enrollment.

A single identified-demographics + consent capture that every participant
completes before reaching either pathway (3B-Triage or TOI). Anchors the
``participant_profiles`` row; the external patient id is stored only as a salted
one-way hash; consent is recorded as ``consent_records``.
"""
