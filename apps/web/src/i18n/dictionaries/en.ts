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
};

// Widened (string-leaf) type so other locales can override any key. English is
// the source of truth, so its shape defines the contract every locale satisfies.
export type Dictionary = typeof en;
