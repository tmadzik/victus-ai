import Link from 'next/link';
import { redirect } from 'next/navigation';

import { PathwayKind, userMayEnterPathway } from '@victus/contracts';

import { Button } from '@/components/ui/button';
import { apiClient } from '@/lib/api-client';
import { auth } from '@/lib/auth';

import { ToiClient } from './toi-client';

export const metadata = { title: 'Pathway B — TOI' };

export default async function TOIPage(): Promise<React.ReactElement> {
  const session = await auth();
  if (!session?.user) redirect('/login');

  // Gate on the CURRENT consents (source of truth), not the JWT.
  const me = await apiClient.me(session.accessToken);
  const decision = userMayEnterPathway(
    PathwayKind.B_TOI,
    session.user.role,
    me.consents,
  );
  if (!decision.allowed) {
    redirect(`/dashboard?blocked_by=${decision.reason}&pathway=B_TOI`);
  }

  await apiClient.enterPathwayB(session.accessToken);

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
            Pathway B
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-brand-950">
            Transdermal Optical Imaging
          </h1>
          <p className="mt-2 max-w-2xl text-brand-700">
            Camera-based rPPG capture with MediaPipe face landmarks for ROI
            tracking. The server runs CHROM and POS chrominance methods in
            parallel and selects whichever yields a higher signal-to-noise
            ratio — both are intentionally green-channel-agnostic so the
            pulse signal survives melanin absorption on Fitzpatrick III–VI
            skin.
          </p>
        </div>
        <Button asChild variant="outline">
          <Link href="/toi/calibration">Calibration study →</Link>
        </Button>
      </header>

      <ToiClient />
    </div>
  );
}
