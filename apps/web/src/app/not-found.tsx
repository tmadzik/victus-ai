import Link from 'next/link';

import { Button } from '@/components/ui/button';

export default function NotFound(): React.ReactElement {
  return (
    <main className="grid min-h-dvh place-items-center px-4 text-center">
      <div className="space-y-4">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
          404
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-brand-950">
          Page not found
        </h1>
        <Button asChild>
          <Link href="/">Return home</Link>
        </Button>
      </div>
    </main>
  );
}
