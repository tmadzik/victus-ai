import { z } from 'zod';

/**
 * Runtime-validated server environment for lead forwarding.
 *
 * Every channel is optional so local development works with zero
 * configuration — `getLeadEnv()` is called lazily inside the server action,
 * never at module load, so builds and static generation never depend on it.
 */
const leadEnvSchema = z.object({
  // SMTP (cPanel-native channel — any mailbox created in cPanel works)
  SMTP_HOST: z.string().min(1).optional(),
  SMTP_PORT: z.coerce.number().int().positive().default(465),
  SMTP_SECURE: z
    .string()
    .optional()
    .transform((v) => v !== 'false' && v !== '0'),
  SMTP_USER: z.string().min(1).optional(),
  SMTP_PASS: z.string().min(1).optional(),
  // Where pilot-request notifications are delivered / sent from
  LEAD_NOTIFY_TO: z.string().email().optional(),
  LEAD_NOTIFY_FROM: z.string().email().optional(),
  // Generic CRM webhook (HubSpot/Zoho/Pipedrive via their inbound webhooks,
  // or an automation bridge like Zapier/Make)
  CRM_WEBHOOK_URL: z.string().url().optional(),
  CRM_WEBHOOK_TOKEN: z.string().min(1).optional(),
});

export type LeadEnv = z.infer<typeof leadEnvSchema>;

let cached: LeadEnv | null = null;

export function getLeadEnv(): LeadEnv {
  if (typeof window !== 'undefined') {
    throw new Error('getLeadEnv must not be called in the browser');
  }
  cached ??= leadEnvSchema.parse({
    SMTP_HOST: process.env.SMTP_HOST,
    SMTP_PORT: process.env.SMTP_PORT,
    SMTP_SECURE: process.env.SMTP_SECURE,
    SMTP_USER: process.env.SMTP_USER,
    SMTP_PASS: process.env.SMTP_PASS,
    LEAD_NOTIFY_TO: process.env.LEAD_NOTIFY_TO,
    LEAD_NOTIFY_FROM: process.env.LEAD_NOTIFY_FROM,
    CRM_WEBHOOK_URL: process.env.CRM_WEBHOOK_URL,
    CRM_WEBHOOK_TOKEN: process.env.CRM_WEBHOOK_TOKEN,
  });
  return cached;
}

export function smtpConfigured(env: LeadEnv): boolean {
  return Boolean(env.SMTP_HOST && env.SMTP_USER && env.SMTP_PASS && env.LEAD_NOTIFY_TO);
}

export function webhookConfigured(env: LeadEnv): boolean {
  return Boolean(env.CRM_WEBHOOK_URL);
}
