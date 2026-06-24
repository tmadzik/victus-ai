import { NextResponse } from 'next/server';

import { KioskCaptureRequestSchema } from '@victus/contracts';

import { apiClient } from '@/lib/api-client';
import { kioskDisabledResponse, kioskEnabled, kioskJson } from '@/lib/kiosk-route';

export const dynamic = 'force-dynamic';

/** POST /api/kiosk/sessions/:id/capture — submit derived capture signals. */
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<Response> {
  if (!kioskEnabled()) return kioskDisabledResponse();
  const { id } = await params;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { error: { code: 'invalid_body', message: 'Expected a JSON body.' } },
      { status: 400 },
    );
  }
  const parsed = KioskCaptureRequestSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: { code: 'invalid_body', message: 'Invalid capture payload.' } },
      { status: 422 },
    );
  }

  return kioskJson(() => apiClient.submitKioskCapture(id, parsed.data));
}
