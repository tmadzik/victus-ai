/** English — the authoritative dictionary. Every other locale derives from this
 * one and overrides only the keys it has a reviewed translation for, so a
 * missing translation always renders as English rather than a blank. */

export const en = {
  language: {
    label: 'Language',
    // Shown when a non-English locale is active, so the English fallback is
    // honest rather than looking broken.
    previewNote:
      'Shona and Ndebele are in preview. Untranslated text appears in English ' +
      'while clinical translations are prepared and reviewed.',
  },
  nav: {
    dashboard: 'Dashboard',
    triage: 'Pathway A — Triage',
    toi: 'Pathway B — TOI',
    history: 'History',
    referrals: 'Referrals',
    clinical: 'Clinical',
    research: 'Research',
    data: 'Data & erasure',
    admin: 'Admin',
    signOut: 'Sign out',
    notifications: 'Notifications',
  },
  dashboard: {
    eyebrow: 'Choose a pathway',
    welcome: 'Welcome',
    intro:
      'Select an assessment pathway. Pathway A surfaces NCD risk with explicit ' +
      'uncertainty; Pathway B captures rPPG biomarkers via the camera.',
    accessBlocked: 'Access blocked',
    startSession: 'Start session',
    pathwayA: {
      title: 'Pathway A — 3B-Triage',
      description:
        'Non-clinical NCD risk via tape-measure + symptom audit. Evidential ' +
        'network outputs GREEN / YELLOW / RED with calibrated uncertainty.',
    },
    pathwayB: {
      title: 'Pathway B — TOI',
      description:
        'Camera-based rPPG biomarkers (HR, RR, BP, HRV, Stress, CVD risk) ' +
        'optimized for Fitzpatrick III–VI via CHROM / POS.',
    },
  },
  // Pathway A wizard chrome. Clinical content (symptom descriptions, risk-class
  // explanations, plausibility messages) is intentionally NOT externalised — it
  // must not be machine-translated without clinical review.
  triage: {
    steps: { inputs: 'Inputs', symptoms: 'Symptom audit', result: 'Result' },
    submissionFailed: 'Submission failed',
    form: {
      title: 'Step 1 · Tape-measure inputs',
      description:
        'Anthropometrics in centimetres and kilograms. Blood pressure is ' +
        'optional but improves classification when available.',
      needsAttention: 'Form needs attention',
      fixFields: 'Please correct the highlighted fields before continuing.',
      height: 'Height (cm)',
      weight: 'Weight (kg)',
      waist: 'Waist (cm)',
      hip: 'Hip (cm, optional)',
      age: 'Age (years)',
      sex: 'Sex',
      systolic: 'Systolic BP (mmHg, optional)',
      diastolic: 'Diastolic BP (mmHg, optional)',
      select: 'Select…',
      male: 'Male',
      female: 'Female',
      other: 'Other',
      working: 'Working…',
      continue: 'Continue to symptom audit',
    },
    symptoms: {
      title: 'Step 2 · Symptom audit',
      triggersRed: 'This will trigger RED',
      back: 'Back',
      submitting: 'Submitting…',
      run: 'Run triage assessment',
    },
    result: {
      title: 'Per-disease risk profile',
      restart: 'Start a new assessment',
      download: 'Download summary',
      summaryTitle: 'Pathway A — NCD risk summary',
    },
  },
  // Pathway B wizard chrome.
  toi: {
    steps: { setup: 'Setup', capture: 'Capture', analyse: 'Analyse', result: 'Result' },
    captureFailed: 'Capture failed',
    analysing: 'Analysing signal…',
    consent: {
      setupTitle: 'Set up your capture environment',
      httpsRequired: 'HTTPS required',
      cameraUnavailable: 'Camera API unavailable',
      instructionsTitle: 'Capture instructions',
      requesting: 'Requesting…',
      requestAccess: 'Request camera access',
    },
    capture: {
      title: 'Capture',
      error: 'Capture error',
      capturing: 'Capturing…',
      useDemoSignal: 'Use demo signal',
      preparing: 'Preparing camera…',
      loadingLandmarker: 'Loading face landmarker…',
      start: 'Start 30-second capture',
    },
    result: {
      recaptureRequired: 'Recapture required',
      warnings: 'Capture warnings',
      restart: 'Start a new capture',
      download: 'Download summary',
      summaryTitle: 'Pathway B — TOI biomarker summary',
    },
  },
};

// Widened (string-leaf) type so other locales can override any key. English is
// the source of truth, so its shape defines the contract every locale satisfies.
export type Dictionary = typeof en;
