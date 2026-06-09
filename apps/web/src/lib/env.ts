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
});

export const publicEnv = publicEnvSchema.parse({
  NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
});

function loadServerEnv(): z.infer<typeof serverEnvSchema> {
  if (typeof window !== 'undefined') {
    throw new Error('serverEnv must not be read in the browser');
  }
  return serverEnvSchema.parse({
    AUTH_SECRET: process.env.AUTH_SECRET,
    AUTH_URL: process.env.AUTH_URL,
    AUTH_TRUST_HOST: process.env.AUTH_TRUST_HOST,
    INTERNAL_API_BASE_URL: process.env.INTERNAL_API_BASE_URL,
    INTERNAL_SERVICE_TOKEN: process.env.INTERNAL_SERVICE_TOKEN,
  });
}

export const serverEnv = typeof window === 'undefined' ? loadServerEnv() : (null as never);
