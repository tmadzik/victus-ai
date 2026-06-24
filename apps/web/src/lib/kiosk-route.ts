/**
 * Shared server helpers for the kiosk `app/api/kiosk/*` route handlers.
 *
 * The browser-side kiosk UI never talks to FastAPI directly — it calls these
 * Next.js route handlers, which hold the per-deployment device token server-side
 * and forward it. This module centralises the config gate and the ApiError →
 * HTTP envelope mapping so every handler stays a one-liner.
 */

import 'server-only';

import { NextResponse } from 'next/server';

import { ApiError } from '@/lib/api-client';
import { serverEnv } from '@/lib/env';

/** True when this deployment is provisioned as a kiosk terminal. */
export function kioskEnabled(): boolean {
  return Boolean(serverEnv.KIOSK_ID && serverEnv.KIOSK_DEVICE_TOKEN);
}

export function kioskDisabledResponse(): NextResponse {
  return NextResponse.json(
    {
      error: {
        code: 'kiosk_disabled',
        message: 'The kiosk rail is not configured on this deployment.',
      },
    },
    { status: 503 },
  );
}

/** Run a proxied call and map the result (or ApiError) to a JSON response. */
export async function kioskJson<T>(fn: () => Promise<T>): Promise<NextResponse> {
  try {
    return NextResponse.json(await fn());
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(
        { error: { code: err.code, message: err.message, details: err.details } },
        { status: err.status },
      );
    }
    // Never leak internals (stack, upstream URL) to a public kiosk client.
    return NextResponse.json(
      { error: { code: 'proxy_error', message: 'Kiosk gateway request failed.' } },
      { status: 502 },
    );
  }
}
