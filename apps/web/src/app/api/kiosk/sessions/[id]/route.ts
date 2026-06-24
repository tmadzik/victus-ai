import { apiClient } from '@/lib/api-client';
import { kioskDisabledResponse, kioskEnabled, kioskJson } from '@/lib/kiosk-route';

export const dynamic = 'force-dynamic';

/** GET /api/kiosk/sessions/:id — poll session status (linked/consented/ready). */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<Response> {
  if (!kioskEnabled()) return kioskDisabledResponse();
  const { id } = await params;
  return kioskJson(() => apiClient.getKioskSessionStatus(id));
}
