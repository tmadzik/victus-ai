import type { Metadata } from 'next';

import { ResultPortal } from './result-portal';

export const metadata: Metadata = {
  title: 'Your secure summary',
  robots: { index: false, follow: false },
};

// Token-gated content must never be cached or statically rendered.
export const dynamic = 'force-dynamic';

export default async function ResultPage({
  params,
}: {
  params: Promise<{ token: string }>;
}): Promise<React.ReactElement> {
  const { token } = await params;
  return <ResultPortal token={token} />;
}
