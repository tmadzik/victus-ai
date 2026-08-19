/**
 * Shared option lists for the demo-request form.
 *
 * These deliberately live outside `app/actions.ts`: a `'use server'` module may
 * only export async functions, so a const exported from there arrives in a
 * client component as a server-action reference rather than an array — which
 * fails at render with "d.map is not a function".
 */

export const ENQUIRY_ROLES = [
  'Health insurer or funder',
  'Clinician or care team',
  'Community or mobile clinic',
  'Other',
] as const;

export const ENQUIRY_COUNTRIES = ['Zimbabwe', 'Nigeria', 'South Africa', 'Other'] as const;
