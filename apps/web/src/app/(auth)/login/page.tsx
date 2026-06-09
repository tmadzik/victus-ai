import type { Metadata } from 'next';

import { LoginForm } from './login-form';

export const metadata: Metadata = { title: 'Sign in' };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ reason?: string }>;
}): Promise<React.ReactElement> {
  const params = await searchParams;
  const reason =
    params.reason === 'session_expired'
      ? 'Your session expired. Please sign in again.'
      : null;
  return <LoginForm initialMessage={reason} />;
}
