import Link from 'next/link';
import type { ReactElement } from 'react';

import { Button } from '@victus/ui';

export default function NotFound(): ReactElement {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-6 px-4 text-center">
      <h1 className="text-brand-950 text-4xl font-semibold tracking-tighter text-balance">
        Page not found.
      </h1>
      <p className="text-brand-700">The page you are looking for does not exist.</p>
      <Button asChild>
        <Link href="/">Back to home</Link>
      </Button>
    </main>
  );
}
