'use server';

import { z } from 'zod';

export interface PilotRequestState {
  status: 'idle' | 'success' | 'error';
  message: string;
}

const pilotRequestSchema = z.object({
  email: z.string().trim().toLowerCase().email('Enter a valid work email.').max(254),
});

/** Bots fill every field; humans never see this one. */
const HONEYPOT_FIELD = 'company_website';

/** Bots submit instantly; humans take at least a moment. */
const MIN_SUBMIT_DELAY_MS = 2_000;

export async function requestPilot(
  _prev: PilotRequestState,
  formData: FormData,
): Promise<PilotRequestState> {
  const honeypot = formData.get(HONEYPOT_FIELD);
  const renderedAt = Number(formData.get('rendered_at'));
  const submittedTooFast =
    Number.isFinite(renderedAt) && Date.now() - renderedAt < MIN_SUBMIT_DELAY_MS;

  // Silently accept bot traffic so automated scripts learn nothing.
  if ((typeof honeypot === 'string' && honeypot.length > 0) || submittedTooFast) {
    return { status: 'success', message: 'Thank you — our team will be in touch shortly.' };
  }

  const parsed = pilotRequestSchema.safeParse({ email: formData.get('email') });
  if (!parsed.success) {
    return {
      status: 'error',
      message: parsed.error.issues[0]?.message ?? 'Enter a valid work email.',
    };
  }

  // POPIA: submission is explicit consent to be contacted about the platform —
  // persist the consent timestamp alongside the lead when the CRM is wired up.
  // TODO(crm): forward to the sales pipeline (CRM / transactional email).
  console.info('[pilot-request]', {
    email: parsed.data.email,
    consentAt: new Date().toISOString(),
  });

  return { status: 'success', message: 'Thank you — our team will be in touch shortly.' };
}
