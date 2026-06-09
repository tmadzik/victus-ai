'use client';

import { SessionProvider } from 'next-auth/react';

/**
 * Client providers mounted once at the root. `SessionProvider` exposes the
 * Auth.js session to client components and, crucially, the `update()` helper —
 * used after a mutation (e.g. granting consent) to refresh the JWT in place so
 * the UI reflects the change without a full sign-out/in.
 */
export function Providers({
  children,
}: {
  children: React.ReactNode;
}): React.ReactElement {
  return <SessionProvider>{children}</SessionProvider>;
}
