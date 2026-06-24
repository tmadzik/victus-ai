import { apiClient } from '@/lib/api-client';
import { kioskDisabledResponse, kioskEnabled, kioskJson } from '@/lib/kiosk-route';

export const dynamic = 'force-dynamic';

/** POST /api/kiosk/sessions — open a new kiosk session, return QR payload. */
export async function POST(): Promise<Response> {
  if (!kioskEnabled()) return kioskDisabledResponse();
  return kioskJson(() => apiClient.createKioskSession());
}
