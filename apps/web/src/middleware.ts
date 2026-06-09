import { NextResponse } from 'next/server';

import { auth } from '@/lib/auth';

// Pathway consent/role gating is enforced in the pathway pages against the
// CURRENT consents (a fresh `/users/me`), not the JWT — so a just-granted
// consent takes effect immediately without waiting for the token to refresh.
// The middleware only handles auth-level concerns.
export default auth((request) => {
  const { auth: session, nextUrl } = request;

  if (!session?.user) {
    return NextResponse.next();
  }

  if (session.error === 'refresh_failed') {
    const loginUrl = nextUrl.clone();
    loginUrl.pathname = '/login';
    loginUrl.searchParams.set('reason', 'session_expired');
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
});

export const config = {
  matcher: ['/((?!api/auth|_next/static|_next/image|favicon.ico|.*\\.svg).*)'],
};
