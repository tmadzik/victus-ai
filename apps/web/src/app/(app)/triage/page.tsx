import { redirect } from 'next/navigation';

import { PathwayKind, userMayEnterPathway } from '@victus/contracts';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { apiClient } from '@/lib/api-client';
import { auth } from '@/lib/auth';

import { TriageClient } from './triage-client';

export const metadata = { title: 'Pathway A — Triage' };

export default async function TriagePage(): Promise<React.ReactElement> {
  const session = await auth();
  if (!session?.user) redirect('/login');

  // Gate on the CURRENT consents (source of truth), not the JWT — so a consent
  // just granted on the dashboard takes effect on this navigation.
  const me = await apiClient.me(session.accessToken);
  const decision = userMayEnterPathway(
    PathwayKind.A_TRIAGE,
    session.user.role,
    me.consents,
  );
  if (!decision.allowed) {
    redirect(`/dashboard?blocked_by=${decision.reason}&pathway=A_TRIAGE`);
  }

  await apiClient.enterPathwayA(session.accessToken);

  return (
    <div className="space-y-8">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
          Pathway A
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-brand-950">
          3B-Triage assessment
        </h1>
        <p className="mt-2 max-w-2xl text-brand-700">
          Tape-measure inputs and a structured symptom audit. Evidential Deep
          Learning surfaces epistemic and aleatoric uncertainty alongside the
          classification. Red-flag symptoms deterministically engage the
          clinical-referral pathway before the network is invoked.
        </p>
      </header>

      <Alert tone="info">
        <AlertTitle>How the state machine works</AlertTitle>
        <AlertDescription>
          <span className="font-semibold">GREEN</span> when the top class is{' '}
          <code className="font-mono">LOW_RISK</code> and vacuity{' '}
          <code className="font-mono">u &lt; 0.5</code>. <br />
          <span className="font-semibold">YELLOW</span> when vacuity exceeds the
          threshold, plausibility flags fire, or the top class is elevated with
          sub-threshold confidence. <br />
          <span className="font-semibold">RED</span> on safety override OR
          high-confidence <code className="font-mono">HIGH_RISK</code>/
          <code className="font-mono">VERY_HIGH_RISK</code> with low vacuity.
        </AlertDescription>
      </Alert>

      <Alert tone="info">
        <AlertTitle>Model: Domain-Adversarial Evidential Deep Learning</AlertTitle>
        <AlertDescription>
          A Dirichlet-EDL classifier with a gradient-reversal domain head
          trained to be invariant across{' '}
          <code className="font-mono">CLINICAL_GRADE</code>,{' '}
          <code className="font-mono">CHW_TAPE_MEASURE</code>, and{' '}
          <code className="font-mono">SYNTHETIC</code> measurement provenance.
          Predictions on tape-measure inputs collected by community health
          workers behave the same as on calibrated clinical instruments — by
          construction, not by hope.
        </AlertDescription>
      </Alert>

      <TriageClient />
    </div>
  );
}
