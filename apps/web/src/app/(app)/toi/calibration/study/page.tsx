import { redirect } from 'next/navigation';

import { PathwayKind, userMayEnterPathway } from '@victus/contracts';

import { auth } from '@/lib/auth';
import {
  getActiveSessionAction,
  listSessionsAction,
  listSubjectsAction,
} from '@/server/study-actions';

import { StudyClient } from './study-client';

export const metadata = { title: 'Study pre-registration' };

export default async function StudyPage(): Promise<React.ReactElement> {
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

  const [subjects, sessions, active] = await Promise.all([
    listSubjectsAction(),
    listSessionsAction(),
    getActiveSessionAction(),
  ]);

  return (
    <div className="space-y-8">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
          Pathway B · Calibration study
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-brand-950">
          Pre-registration + cohort metadata
        </h1>
        <p className="mt-2 max-w-3xl text-brand-700">
          Enrol anonymous study subjects and lock the cohort context for each
          capture session — posture, ambient lux, time-of-day, caffeine /
          nicotine / exercise covariates. Every calibration pair recorded while
          a session is active automatically inherits this context, enabling
          stratified Bland-Altman analysis and per-subject repeated-measures
          tracking.
        </p>
      </header>

      <StudyClient
        initialSubjects={subjects}
        initialSessions={sessions}
        initialActive={active}
      />
    </div>
  );
}
