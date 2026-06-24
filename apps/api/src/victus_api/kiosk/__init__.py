"""Mobile Clinic Gateway — public-kiosk capture rail.

Reuses the shared identity (``users``), conversation (``whatsapp_sessions``) and
async-processing (``processing_jobs``) rails rather than forking them. See
``db.models`` (KioskSession / KioskBiometricMetadata / KioskClinicalResult /
KioskResultToken) for the schema this package operates on.
"""
