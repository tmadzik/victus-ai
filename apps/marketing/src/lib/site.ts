/** Canonical origins for the decoupled environments. */
export const SITE_URL = 'https://www.victusdata.com';

/** The clinical application lives on its own subdomain — auth never crosses over. */
export const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? 'https://app.victusdata.com';

export const SITE_NAME = 'Victus';
export const LEGAL_NAME = 'Victus Data Innovations';
