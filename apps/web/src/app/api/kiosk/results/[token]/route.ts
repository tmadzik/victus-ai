import { apiClient } from '@/lib/api-client';
import { kioskJson } from '@/lib/kiosk-route';

export const dynamic = 'force-dynamic';

/** GET /api/kiosk/results/:token — probe a result link (public, no data). */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ token: string }> },
): Promise<Response> {
  const { token } = await params;
  return kioskJson(() => apiClient.getKioskResultGate(token));
}
