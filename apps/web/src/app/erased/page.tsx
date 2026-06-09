import Link from 'next/link';

import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';

export const metadata = { title: 'Account erased' };

export default function ErasedPage(): React.ReactElement {
  return (
    <main className="grid min-h-dvh place-items-center px-4 py-12">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
            Erasure completed
          </p>
          <CardTitle className="mt-1 text-2xl">Your account has been erased</CardTitle>
          <CardDescription>
            GDPR Article 17 / POPIA section 24 request honoured.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm leading-relaxed text-brand-800">
          <p>
            Your identifying fields (email, name, password) have been
            tombstoned and your active sessions revoked. You can no longer log
            in with these credentials.
          </p>
          <p>
            Your study subjects were anonymised via salted SHA-256 — the
            de-identified biometric records they participated in are retained
            under the research-retention exception (GDPR Art 17(3)(d) / POPIA
            s14(3)) but can no longer be linked back to a natural person.
          </p>
          <p>
            The audit-log entries that reference your historical user ID are
            preserved as regulatory evidence that the erasure was performed.
          </p>
          <p>
            If you want to use Victus AI again, you can register a new account
            with the same email address.
          </p>
          <div className="flex justify-end gap-3 pt-2">
            <Button asChild>
              <Link href="/">Home</Link>
            </Button>
            <Button asChild variant="outline">
              <Link href="/register">Create a new account</Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
