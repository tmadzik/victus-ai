import { NextResponse } from 'next/server';

import { auth } from '@/lib/auth';
import { PathwayKind, userMayEnterPathway } from '@victus/contracts';

const PATHWAY_PATHS: Record<string, PathwayKind> = {
  '/triage': PathwayKind.A_TRIAGE,
  '/toi': PathwayKind.B_TOI,
};

export default auth((request) => {
  const { auth: session, nextUrl } = request;
  const { pathname } = nextUrl;

  if (!session?.user) {
    return NextResponse.next();
  }

  if (session.error === 'refresh_failed') {
    const loginUrl = nextUrl.clone();
    loginUrl.pathname = '/login';
    loginUrl.searchParams.set('reason', 'session_expired');
    return NextResponse.redirect(loginUrl);
  }

  for (const [prefix, pathway] of Object.entries(PATHWAY_PATHS)) {
    if (pathname === prefix || pathname.startsWith(`${prefix}/`)) {
      const decision = userMayEnterPathway(
        pathway,
        session.user.role,
        session.user.consents,
      );
      if (!decision.allowed) {
        const dashboardUrl = nextUrl.clone();
        dashboardUrl.pathname = '/dashboard';
        dashboardUrl.searchParams.set('blocked_by', decision.reason);
        dashboardUrl.searchParams.set('pathway', pathway);
        return NextResponse.redirect(dashboardUrl);
      }
    }
  }

  return NextResponse.next();
});

export const config = {
  matcher: ['/((?!api/auth|_next/static|_next/image|favicon.ico|.*\\.svg).*)'],
};
