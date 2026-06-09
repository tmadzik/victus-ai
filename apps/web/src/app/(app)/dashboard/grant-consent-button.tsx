'use client';

import { useSession } from 'next-auth/react';
import { useRouter } from 'next/navigation';
import { useState, useTransition } from 'react';

import type { ConsentType } from '@victus/contracts';

import { Button } from '@/components/ui/button';
import { grantConsentAction } from '@/server/consent-actions';

/**
 * Grant the consent a pathway requires, then enter it — without a sign-out/in.
 *
 * Flow: persist the grant (server action) → `update()` to re-run the Auth.js
 * `jwt` callback (which re-fetches `/users/me`, refreshing `session.user.consents`)
 * → navigate into the pathway and revalidate server components.
 */
export function GrantConsentButton({
  consents,
  href,
}: {
  consents: ConsentType[];
  href: '/triage' | '/toi';
}): React.ReactElement {
  const { update } = useSession();
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  const onGrant = (): void => {
    setError(null);
    startTransition(async () => {
      const result = await grantConsentAction(consents);
      if (!result.ok) {
        setError(result.error);
        return;
      }
      await update();
      router.push(href);
      router.refresh();
    });
  };

  return (
    <div className="space-y-2">
      <p className="text-sm text-brand-600">
        This pathway needs your consent:{' '}
        <span className="font-medium text-brand-800">{consents.join(', ')}</span>
      </p>
      {error ? (
        <p className="text-sm text-[color:var(--color-state-red-ring)]">{error}</p>
      ) : null}
      <Button type="button" onClick={onGrant} disabled={isPending}>
        {isPending ? 'Granting…' : 'Grant consent & start'}
      </Button>
    </div>
  );
}
