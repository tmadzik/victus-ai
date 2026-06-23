'use client';

import Link from 'next/link';

import {
  POSTURE_LABELS,
  type StudySessionResponse,
  TIME_OF_DAY_LABELS,
} from '@victus/contracts';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';

/**
 * Shown on the calibration page when the researcher has an active session.
 * Makes it visceral that the next capture will inherit the session context.
 */
export function ActiveSessionBanner({
  session,
}: {
  session: StudySessionResponse;
}): React.ReactElement {
  return (
    <Alert tone="success">
      <AlertTitle className="flex flex-wrap items-center gap-2">
        <Badge tone="green">SESSION</Badge>
        Subject {session.external_subject_id}
        <span className="text-xs text-brand-600">
          · started{' '}
          {new Date(session.session_started_at).toLocaleString('en-GB', {
            dateStyle: 'short',
            timeStyle: 'short',
          })}
        </span>
      </AlertTitle>
      <AlertDescription>
        New captures will auto-attach to this session.{' '}
        <span className="font-mono text-xs">
          {POSTURE_LABELS[session.posture]} · {TIME_OF_DAY_LABELS[session.time_of_day]}
          {session.recording_site_label ? ` · ${session.recording_site_label}` : ''}
        </span>
        . Manage subjects + sessions at{' '}
        <Link
          href="/toi/calibration/study"
          className="font-semibold underline"
        >
          /toi/calibration/study
        </Link>
        .
      </AlertDescription>
    </Alert>
  );
}

export function NoActiveSessionBanner(): React.ReactElement {
  return (
    <Alert tone="info">
      <AlertTitle>No active study session</AlertTitle>
      <AlertDescription>
        You can still record pairs manually, but they won&apos;t be stratified
        by posture / time-of-day / subject.{' '}
        <Link
          href="/toi/calibration/study"
          className="font-semibold underline"
        >
          Enrol a subject and start a session
        </Link>{' '}
        to enable IRB-grade tracking.
      </AlertDescription>
    </Alert>
  );
}
