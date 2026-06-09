'use client';

import { useState, useTransition } from 'react';

import type { ConsentType } from '@victus/contracts';

import { Button } from '@/components/ui/button';
import { grantConsentAction } from '@/server/consent-actions';

/**
 * Grant the consent a pathway requires, then enter it — no sign-out/in.
 *
 * The grant is persisted (server action) and the pathway page re-reads the
 * current consents server-side, so a plain navigation is enough.
 */
export function GrantConsentButton({
  consents,
  href,
}: {
  consents: ConsentType[];
  href: '/triage' | '/toi';
}): React.ReactElement {
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
      window.location.assign(href);
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
