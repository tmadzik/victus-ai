import { NextResponse } from 'next/server';

import { UserRole } from '@victus/contracts';

import { ApiError, apiClient } from '@/lib/api-client';
import { auth } from '@/lib/auth';

export const dynamic = 'force-dynamic';

/** POST /api/organisation/attestation — record the care-use declaration.
 *
 *  A thin authenticated proxy: the care manager's access token stays
 *  server-side and FastAPI re-checks the role, writes the attestation and
 *  audits it. The role check here only avoids a pointless round trip — it is
 *  not the control, because a browser-side check never is. */
export async function POST(): Promise<Response> {
  const session = await auth();
  if (!session?.user || session.user.role !== UserRole.CARE_MANAGER) {
    return NextResponse.json(
      {
        error: {
          code: 'forbidden',
          message: 'Only a care manager can give the care-use confirmation.',
        },
      },
      { status: 403 },
    );
  }

  try {
    const result = await apiClient.recordAttestation(session.accessToken);
    return NextResponse.json(result, { status: 201 });
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(
        { error: { code: err.code, message: err.message } },
        { status: err.status },
      );
    }
    return NextResponse.json(
      { error: { code: 'upstream_error', message: 'Could not record it.' } },
      { status: 502 },
    );
  }
}
