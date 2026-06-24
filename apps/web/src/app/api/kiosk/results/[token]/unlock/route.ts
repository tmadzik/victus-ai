import { NextResponse } from 'next/server';
import { z } from 'zod';

import { apiClient } from '@/lib/api-client';
import { kioskJson } from '@/lib/kiosk-route';

export const dynamic = 'force-dynamic';

const UnlockBodySchema = z.object({ otp: z.string().regex(/^\d{4}$/) });

/** POST /api/kiosk/results/:token/unlock — OTP unlock (public, single use). */
export async function POST(
  request: Request,
  { params }: { params: Promise<{ token: string }> },
): Promise<Response> {
  const { token } = await params;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { error: { code: 'invalid_body', message: 'Expected a JSON body.' } },
      { status: 400 },
    );
  }
  const parsed = UnlockBodySchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: { code: 'invalid_otp', message: 'Enter the 4-digit code.' } },
      { status: 422 },
    );
  }

  return kioskJson(() => apiClient.unlockKioskResult(token, parsed.data.otp));
}
