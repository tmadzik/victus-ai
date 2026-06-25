import { NextResponse } from 'next/server';

import { UserRole } from '@victus/contracts';

import { ApiError, apiClient } from '@/lib/api-client';
import { auth } from '@/lib/auth';

export const dynamic = 'force-dynamic';

const CLINICAL_ROLES: readonly UserRole[] = [UserRole.CLINICIAN, UserRole.ADMIN];

/** GET /api/clinical/:userId/report — stream the participant-record PDF.
 *
 *  The clinician's session access token is held server-side and forwarded to
 *  FastAPI; the browser never sees it. FastAPI re-checks the role and audits the
 *  export, so this handler is a thin authenticated proxy. */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ userId: string }> },
): Promise<Response> {
  const session = await auth();
  if (!session?.user || !CLINICAL_ROLES.includes(session.user.role)) {
    return NextResponse.json(
      { error: { code: 'forbidden', message: 'Clinician access required.' } },
      { status: 403 },
    );
  }

  const { userId } = await params;
  try {
    const { bytes, filename } = await apiClient.getParticipantReportPdf(
      session.accessToken,
      userId,
    );
    return new NextResponse(bytes, {
      status: 200,
      headers: {
        'Content-Type': 'application/pdf',
        'Content-Disposition': `attachment; filename="${filename}"`,
        'Cache-Control': 'no-store',
      },
    });
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(
        { error: { code: err.code, message: err.message } },
        { status: err.status },
      );
    }
    return NextResponse.json(
      { error: { code: 'proxy_error', message: 'Could not generate the PDF.' } },
      { status: 502 },
    );
  }
}
