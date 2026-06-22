import Link from 'next/link';
import { redirect } from 'next/navigation';

import { type ConsentType, PathwayKind, userMayEnterPathway } from '@victus/contracts';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { getI18n } from '@/i18n';
import { apiClient } from '@/lib/api-client';
import { auth } from '@/lib/auth';

import { GrantConsentButton } from './grant-consent-button';

const REASON_COPY: Record<string, string> = {
  role: 'Your account role is not permitted for that pathway.',
  consent: 'Required consent must be granted before entering that pathway.',
};

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ blocked_by?: string; pathway?: string }>;
}): Promise<React.ReactElement> {
  const session = await auth();
  if (!session?.user) redirect('/login');

  const { dict } = await getI18n();
  const d = dict.dashboard;

  const params = await searchParams;
  const blocker = params.blocked_by ? REASON_COPY[params.blocked_by] : null;

  // Read current consents from the source of truth so the cards reflect a
  // grant immediately (the JWT may lag a freshly-granted consent).
  let consents = session.user.consents;
  try {
    consents = (await apiClient.me(session.accessToken)).consents;
  } catch {
    // fall back to the token's consents if the fresh fetch fails
  }
  const a = userMayEnterPathway(PathwayKind.A_TRIAGE, session.user.role, consents);
  const b = userMayEnterPathway(PathwayKind.B_TOI, session.user.role, consents);

  return (
    <div className="space-y-8">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
          {d.eyebrow}
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-brand-950">
          {d.welcome}, {session.user.name ?? 'clinician'}
        </h1>
        <p className="mt-2 max-w-2xl text-brand-700">{d.intro}</p>
      </header>

      {blocker ? (
        <Alert tone="warning">
          <AlertTitle>{d.accessBlocked}</AlertTitle>
          <AlertDescription>
            {blocker}{' '}
            {params.pathway ? <span className="font-semibold">({params.pathway})</span> : null}
          </AlertDescription>
        </Alert>
      ) : null}

      <section className="grid gap-6 sm:grid-cols-2">
        <PathwayCard
          title={d.pathwayA.title}
          description={d.pathwayA.description}
          startLabel={d.startSession}
          href="/triage"
          decision={a}
        />
        <PathwayCard
          title={d.pathwayB.title}
          description={d.pathwayB.description}
          startLabel={d.startSession}
          href="/toi"
          decision={b}
        />
      </section>
    </div>
  );
}

function describe(
  decision: ReturnType<typeof userMayEnterPathway>,
): string {
  if (decision.allowed) return '';
  if (decision.reason === 'role') {
    return `Requires one of: ${decision.missing.join(', ')}`;
  }
  return `Missing consent: ${decision.missing.join(', ')}`;
}

function PathwayCard({
  title,
  description,
  startLabel,
  href,
  decision,
}: {
  title: string;
  description: string;
  startLabel: string;
  href: '/triage' | '/toi';
  decision: ReturnType<typeof userMayEnterPathway>;
}): React.ReactElement {
  const enabled = decision.allowed;
  return (
    <Card className={enabled ? '' : 'opacity-90'}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        {enabled ? (
          <Button asChild>
            <Link href={href}>{startLabel}</Link>
          </Button>
        ) : decision.reason === 'consent' ? (
          <GrantConsentButton
            consents={decision.missing as ConsentType[]}
            href={href}
          />
        ) : (
          <p className="text-sm text-brand-600">{describe(decision)}</p>
        )}
      </CardContent>
    </Card>
  );
}
