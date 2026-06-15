'use client';

import { useEffect, type ReactElement } from 'react';

import { Button } from '@victus/ui';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}): ReactElement {
  useEffect(() => {
    // Surfaced in the Passenger log on cPanel for diagnosis.
    console.error(error);
  }, [error]);

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-6 px-4 text-center">
      <h1 className="text-brand-950 text-4xl font-semibold tracking-tighter text-balance">
        Something went wrong.
      </h1>
      <p className="text-brand-700 max-w-md text-pretty">
        An unexpected error occurred. Please try again, or email{' '}
        <a href="mailto:pilots@victusdata.com" className="underline underline-offset-2">
          pilots@victusdata.com
        </a>{' '}
        if it persists.
      </p>
      <Button onClick={() => reset()}>Try again</Button>
    </main>
  );
}
