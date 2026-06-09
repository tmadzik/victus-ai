import Link from 'next/link';
import { redirect } from 'next/navigation';

import { PathwayKind, userMayEnterPathway } from '@victus/contracts';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { auth } from '@/lib/auth';

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

  const params = await searchParams;
  const blocker = params.blocked_by ? REASON_COPY[params.blocked_by] : null;

  const a = userMayEnterPathway(
    PathwayKind.A_TRIAGE,
    session.user.role,
    session.user.consents,
  );
  const b = userMayEnterPathway(
    PathwayKind.B_TOI,
    session.user.role,
    session.user.consents,
  );

  return (
    <div className="space-y-8">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
          Choose a pathway
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-brand-950">
          Welcome, {session.user.name ?? 'clinician'}
        </h1>
        <p className="mt-2 max-w-2xl text-brand-700">
          Select an assessment pathway. Pathway A surfaces NCD risk with explicit
          uncertainty; Pathway B captures rPPG biomarkers via the camera.
        </p>
      </header>

      {blocker ? (
        <Alert tone="warning">
          <AlertTitle>Access blocked</AlertTitle>
          <AlertDescription>
            {blocker}{' '}
            {params.pathway ? <span className="font-semibold">({params.pathway})</span> : null}
          </AlertDescription>
        </Alert>
      ) : null}

      <section className="grid gap-6 sm:grid-cols-2">
        <PathwayCard
          title="Pathway A — 3B-Triage"
          description="Non-clinical NCD risk via tape-measure + symptom audit. Evidential network outputs GREEN / YELLOW / RED with calibrated uncertainty."
          href="/triage"
          enabled={a.allowed}
          requirement={a.allowed ? null : describe(a)}
        />
        <PathwayCard
          title="Pathway B — TOI"
          description="Camera-based rPPG biomarkers (HR, RR, BP, HRV, Stress, CVD risk) optimized for Fitzpatrick III–VI via CHROM / POS."
          href="/toi"
          enabled={b.allowed}
          requirement={b.allowed ? null : describe(b)}
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
  href,
  enabled,
  requirement,
}: {
  title: string;
  description: string;
  href: '/triage' | '/toi';
  enabled: boolean;
  requirement: string | null;
}): React.ReactElement {
  return (
    <Card className={enabled ? '' : 'opacity-70'}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="flex items-center justify-between">
        {enabled ? (
          <Button asChild>
            <Link href={href}>Start session</Link>
          </Button>
        ) : (
          <p className="text-sm text-brand-600">{requirement}</p>
        )}
      </CardContent>
    </Card>
  );
}
