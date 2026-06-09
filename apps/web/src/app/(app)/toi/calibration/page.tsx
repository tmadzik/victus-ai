import { redirect } from 'next/navigation';

import { PathwayKind, userMayEnterPathway } from '@victus/contracts';

import { auth } from '@/lib/auth';
import {
  getCalibrationStatsAction,
  listCalibrationRecordsAction,
} from '@/server/calibration-actions';
import { getActiveSessionAction } from '@/server/study-actions';

import { CalibrationClient } from './calibration-client';

export const metadata = { title: 'rPPG Calibration Study' };

export default async function CalibrationPage(): Promise<React.ReactElement> {
  const session = await auth();
  if (!session?.user) redirect('/login');

  const decision = userMayEnterPathway(
    PathwayKind.B_TOI,
    session.user.role,
    session.user.consents,
  );
  if (!decision.allowed) {
    redirect(`/dashboard?blocked_by=${decision.reason}&pathway=B_TOI`);
  }

  const [stats, records, activeSession] = await Promise.all([
    getCalibrationStatsAction(),
    listCalibrationRecordsAction(50),
    getActiveSessionAction(),
  ]);

  return (
    <div className="space-y-8">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
          Pathway B · Calibration study
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-brand-950">
          rPPG vs reference-device agreement
        </h1>
        <p className="mt-2 max-w-3xl text-brand-700">
          Each capture you pair with an independent reference reading (pulse
          oximeter, smart watch, ECG strap, or carefully-counted carotid pulse)
          becomes a Bland-Altman datapoint. When a pre-registered study session
          is active, captures auto-attach and contribute to posture /
          time-of-day / per-subject stratifications.
        </p>
      </header>

      <CalibrationClient
        initialStats={stats}
        initialRecords={records}
        initialActiveSession={activeSession}
      />
    </div>
  );
}
