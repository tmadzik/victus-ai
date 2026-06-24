/**
 * Runtime-validated environment variables.
 *
 * Public vars (`NEXT_PUBLIC_*`) are inlined by Next.js at build-time and are
 * safe to read in both server and client contexts. Server-only vars are
 * never imported into client bundles — we guard with a process check.
 */

import { z } from 'zod';

const publicEnvSchema = z.object({
  NEXT_PUBLIC_API_BASE_URL: z.string().url(),
});

const serverEnvSchema = z.object({
  AUTH_SECRET: z.string().min(32, 'AUTH_SECRET must be at least 32 chars'),
  AUTH_URL: z.string().url().optional(),
  AUTH_TRUST_HOST: z
    .string()
    .optional()
    .transform((v) => v === 'true' || v === '1'),
  INTERNAL_API_BASE_URL: z.string().url(),
  INTERNAL_SERVICE_TOKEN: z.string().min(16),
  // Kiosk terminal identity for this deployment. The Next.js server holds the
  // device token (never the browser) and forwards it to FastAPI as
  // X-Kiosk-Id / X-Kiosk-Token. Optional: unset disables the kiosk rail on
  // this instance (the route handlers return 503).
  KIOSK_ID: z.string().optional(),
  KIOSK_DEVICE_TOKEN: z.string().optional(),
});

export const publicEnv = publicEnvSchema.parse({
  NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
});

// When packaging the cPanel bundle we run `next build` with no server secrets
// (they live in the cPanel Node.js app screen, set at runtime). This escape
// hatch lets the build's page-data collection pass without them. It is NOT set
// when the standalone server actually starts, so real runtime requests are
// still validated strictly below.
const skipServerEnvValidation =
  process.env.SKIP_ENV_VALIDATION === '1' || process.env.SKIP_ENV_VALIDATION === 'true';

function loadServerEnv(): z.infer<typeof serverEnvSchema> {
  if (typeof window !== 'undefined') {
    throw new Error('serverEnv must not be read in the browser');
  }
  return serverEnvSchema.parse({
    AUTH_SECRET:
      process.env.AUTH_SECRET ?? (skipServerEnvValidation ? 'x'.repeat(32) : undefined),
    AUTH_URL: process.env.AUTH_URL,
    AUTH_TRUST_HOST: process.env.AUTH_TRUST_HOST,
    INTERNAL_API_BASE_URL:
      process.env.INTERNAL_API_BASE_URL ??
      (skipServerEnvValidation ? 'http://localhost' : undefined),
    INTERNAL_SERVICE_TOKEN:
      process.env.INTERNAL_SERVICE_TOKEN ??
      (skipServerEnvValidation ? 'x'.repeat(16) : undefined),
    KIOSK_ID: process.env.KIOSK_ID,
    KIOSK_DEVICE_TOKEN: process.env.KIOSK_DEVICE_TOKEN,
  });
}

export const serverEnv = typeof window === 'undefined' ? loadServerEnv() : (null as never);
