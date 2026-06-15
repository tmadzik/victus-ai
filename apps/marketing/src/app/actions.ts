'use server';

import { z } from 'zod';

import { forwardLead } from '@/lib/leads';

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

const SUCCESS: PilotRequestState = {
  status: 'success',
  message: 'Thank you — our team will be in touch shortly.',
};

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
    return SUCCESS;
  }

  const parsed = pilotRequestSchema.safeParse({ email: formData.get('email') });
  if (!parsed.success) {
    return {
      status: 'error',
      message: parsed.error.issues[0]?.message ?? 'Enter a valid work email.',
    };
  }

  // POPIA: submission is explicit consent to be contacted about the platform —
  // the consent timestamp travels with the lead on every channel.
  const lead = {
    email: parsed.data.email,
    consentAt: new Date().toISOString(),
    source: 'www.victusdata.com/#request-pilot',
  };

  const result = await forwardLead(lead);

  if (result.unconfigured) {
    // Dev / misconfigured deployment: never lose the lead silently.
    console.error(
      '[pilot-request] NO DELIVERY CHANNEL CONFIGURED — set SMTP_* + LEAD_NOTIFY_TO ' +
        'and/or CRM_WEBHOOK_URL. Lead logged below so it is not lost:',
      lead,
    );
    return SUCCESS;
  }

  const failed = result.channels.filter((c) => !c.ok);
  if (failed.length > 0) {
    console.error('[pilot-request] channel failure(s):', failed, 'lead:', lead);
  }

  if (!result.delivered) {
    return {
      status: 'error',
      message: 'Something went wrong on our side. Please email pilots@victusdata.com directly.',
    };
  }

  console.info('[pilot-request] delivered', {
    email: lead.email,
    consentAt: lead.consentAt,
    channels: result.channels.map((c) => c.name),
  });
  return SUCCESS;
}
