import nodemailer from 'nodemailer';

import { getLeadEnv, smtpConfigured, webhookConfigured } from '@/lib/env';

export interface PilotLead {
  email: string;
  /** ISO timestamp of the POPIA consent given by submitting the form. */
  consentAt: string;
  source: string;
}

export interface ForwardResult {
  /** True when at least one configured channel accepted the lead. */
  delivered: boolean;
  /** True when no channel is configured at all (dev / misconfiguration). */
  unconfigured: boolean;
  channels: { name: 'smtp' | 'webhook'; ok: boolean; error?: string }[];
}

const WEBHOOK_TIMEOUT_MS = 8_000;

async function sendSmtp(lead: PilotLead): Promise<void> {
  const env = getLeadEnv();
  const transport = nodemailer.createTransport({
    host: env.SMTP_HOST,
    port: env.SMTP_PORT,
    secure: env.SMTP_SECURE,
    auth: { user: env.SMTP_USER, pass: env.SMTP_PASS },
  });

  await transport.sendMail({
    from: env.LEAD_NOTIFY_FROM ?? env.SMTP_USER,
    to: env.LEAD_NOTIFY_TO,
    replyTo: lead.email,
    subject: `New pilot request — ${lead.email}`,
    text: [
      'A new pilot request was submitted on www.victusdata.com.',
      '',
      `Work email:      ${lead.email}`,
      `Consent given:   ${lead.consentAt} (POPIA — contact about the Victus platform)`,
      `Source:          ${lead.source}`,
      '',
      'Reply directly to this email to reach the lead.',
    ].join('\n'),
  });
}

async function sendWebhook(lead: PilotLead): Promise<void> {
  const env = getLeadEnv();
  const response = await fetch(env.CRM_WEBHOOK_URL as string, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(env.CRM_WEBHOOK_TOKEN ? { Authorization: `Bearer ${env.CRM_WEBHOOK_TOKEN}` } : {}),
    },
    body: JSON.stringify({
      type: 'pilot_request',
      email: lead.email,
      consent_at: lead.consentAt,
      consent_basis: 'POPIA explicit consent — contact about the Victus platform',
      source: lead.source,
    }),
    signal: AbortSignal.timeout(WEBHOOK_TIMEOUT_MS),
  });
  if (!response.ok) {
    throw new Error(`webhook responded ${response.status}`);
  }
}

/**
 * Forwards a lead to every configured channel. Channels run in parallel and
 * fail independently — one healthy channel is enough to count as delivered.
 */
export async function forwardLead(lead: PilotLead): Promise<ForwardResult> {
  const env = getLeadEnv();
  const channels: ForwardResult['channels'] = [];

  const attempts: Promise<void>[] = [];
  if (smtpConfigured(env)) {
    attempts.push(
      sendSmtp(lead).then(
        () => void channels.push({ name: 'smtp', ok: true }),
        (err: unknown) => void channels.push({ name: 'smtp', ok: false, error: String(err) }),
      ),
    );
  }
  if (webhookConfigured(env)) {
    attempts.push(
      sendWebhook(lead).then(
        () => void channels.push({ name: 'webhook', ok: true }),
        (err: unknown) => void channels.push({ name: 'webhook', ok: false, error: String(err) }),
      ),
    );
  }

  if (attempts.length === 0) {
    return { delivered: false, unconfigured: true, channels: [] };
  }

  await Promise.all(attempts);
  return {
    delivered: channels.some((c) => c.ok),
    unconfigured: false,
    channels,
  };
}
