'use client';

import Link from 'next/link';
import { useCallback, useState, useTransition } from 'react';

import type {
  StudySessionResponse,
  StudySubjectResponse,
} from '@victus/contracts';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  ErasureBasis,
  ErasureJurisdiction,
  POSTURE_LABELS,
  TIME_OF_DAY_LABELS,
} from '@victus/contracts';
import { anonymiseSubjectAction } from '@/server/governance-actions';
import {
  endSessionAction,
  getActiveSessionAction,
  listSessionsAction,
  listSubjectsAction,
} from '@/server/study-actions';

import { SessionForm } from './session-form';
import { SubjectForm } from './subject-form';

export function StudyClient({
  initialSubjects,
  initialSessions,
  initialActive,
}: {
  initialSubjects: StudySubjectResponse[];
  initialSessions: StudySessionResponse[];
  initialActive: StudySessionResponse | null;
}): React.ReactElement {
  const [subjects, setSubjects] =
    useState<StudySubjectResponse[]>(initialSubjects);
  const [sessions, setSessions] =
    useState<StudySessionResponse[]>(initialSessions);
  const [active, setActive] = useState<StudySessionResponse | null>(
    initialActive,
  );
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const refresh = useCallback((): void => {
    startTransition(async () => {
      const [s, sessionList, a] = await Promise.all([
        listSubjectsAction(),
        listSessionsAction(),
        getActiveSessionAction(),
      ]);
      setSubjects(s);
      setSessions(sessionList);
      setActive(a);
    });
  }, []);

  const onSubjectCreated = useCallback(
    (subject: StudySubjectResponse): void => {
      setSubjects((prev) => [subject, ...prev]);
    },
    [],
  );

  const onSessionStarted = useCallback(
    (sessionRow: StudySessionResponse): void => {
      setActive(sessionRow);
      setSessions((prev) => [sessionRow, ...prev]);
    },
    [],
  );

  const endActive = useCallback((): void => {
    if (!active) return;
    setError(null);
    startTransition(async () => {
      const result = await endSessionAction(active.id, { notes: null });
      if (!result.ok) {
        setError(result.error);
      } else {
        setActive(null);
        setSessions((prev) =>
          prev.map((row) => (row.id === result.value.id ? result.value : row)),
        );
      }
    });
  }, [active]);

  const onAnonymise = useCallback((subjectId: string, externalId: string): void => {
    if (
      !confirm(
        `Anonymise subject ${externalId}?\n\nThis is irreversible: the external ID will be rotated to a salted hash, medical history + anthropometrics cleared, and the subject deactivated. Calibration pairs are retained as de-identified data.`,
      )
    ) {
      return;
    }
    setError(null);
    startTransition(async () => {
      const result = await anonymiseSubjectAction(subjectId, {
        jurisdiction: ErasureJurisdiction.POPIA,
        request_basis: ErasureBasis.WITHDRAWN_CONSENT,
        notes: null,
      });
      if (!result.ok) {
        setError(result.error);
      } else {
        refresh();
      }
    });
  }, [refresh]);

  return (
    <div className="space-y-8">
      {error ? (
        <Alert tone="danger">
          <AlertTitle>Action failed</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <ActiveSessionBlock
        active={active}
        onEnd={endActive}
        isPending={isPending}
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <SubjectForm onCreated={onSubjectCreated} />
        <SessionForm
          subjects={subjects}
          onStarted={onSessionStarted}
          activeSession={active}
        />
      </div>

      <SubjectsList
        subjects={subjects}
        onRefresh={refresh}
        onAnonymise={onAnonymise}
      />

      <SessionsList sessions={sessions} />

      <Card>
        <CardFooter className="flex items-center justify-between">
          <p className="text-xs text-brand-600">
            Records and stats live at{' '}
            <Link href="/toi/calibration" className="font-semibold underline">
              /toi/calibration
            </Link>
            . Capture while a session is active to auto-attach pairs.
          </p>
          <Button asChild>
            <Link href="/toi/calibration">Go to capture</Link>
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}

function ActiveSessionBlock({
  active,
  onEnd,
  isPending,
}: {
  active: StudySessionResponse | null;
  onEnd: () => void;
  isPending: boolean;
}): React.ReactElement {
  if (!active) {
    return (
      <Alert tone="info">
        <AlertTitle>No active session</AlertTitle>
        <AlertDescription>
          Start a session below before capturing — pairs recorded without an
          active session can still be paired manually, but they will not
          contribute to the posture / time-of-day / per-subject stratifications.
        </AlertDescription>
      </Alert>
    );
  }
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
              Active session
            </p>
            <CardTitle className="mt-1 flex flex-wrap items-center gap-2 text-lg">
              <span>Subject {active.external_subject_id}</span>
              <Badge tone="green">
                {active.is_locked ? 'LOCKED' : 'UNLOCKED'}
              </Badge>
            </CardTitle>
            <CardDescription>
              Started {new Date(active.session_started_at).toLocaleString('en-ZA')}{' '}
              · {active.pair_count} pair{active.pair_count === 1 ? '' : 's'}{' '}
              recorded so far
            </CardDescription>
          </div>
          <Button onClick={onEnd} variant="outline" disabled={isPending}>
            End session
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Cell label="Posture" value={POSTURE_LABELS[active.posture]} />
          <Cell label="Time of day" value={TIME_OF_DAY_LABELS[active.time_of_day]} />
          <Cell
            label="Ambient lux"
            value={active.ambient_lux !== null ? `${active.ambient_lux.toFixed(0)} lx` : '—'}
          />
          <Cell
            label="Temp / humidity"
            value={
              [
                active.ambient_temperature_c !== null
                  ? `${active.ambient_temperature_c.toFixed(1)} °C`
                  : null,
                active.room_humidity_pct !== null
                  ? `${active.room_humidity_pct.toFixed(0)}% RH`
                  : null,
              ]
                .filter(Boolean)
                .join(' · ') || '—'
            }
          />
          <Cell
            label="Caffeine ≤ 2h"
            value={active.caffeine_within_2h ? 'YES' : 'no'}
          />
          <Cell
            label="Nicotine ≤ 2h"
            value={active.nicotine_within_2h ? 'YES' : 'no'}
          />
          <Cell
            label="Alcohol ≤ 24h"
            value={active.alcohol_within_24h ? 'YES' : 'no'}
          />
          <Cell
            label="Last exercise"
            value={
              active.last_exercise_hours_ago !== null
                ? `${active.last_exercise_hours_ago.toFixed(1)} h ago`
                : '—'
            }
          />
        </dl>
        <p className="mt-3 text-xs text-brand-600">
          Protocol{' '}
          <code className="font-mono">{active.protocol_version}</code>
          {active.recording_site_label ? (
            <> · site {active.recording_site_label}</>
          ) : null}
        </p>
      </CardContent>
    </Card>
  );
}

function SubjectsList({
  subjects,
  onRefresh,
  onAnonymise,
}: {
  subjects: StudySubjectResponse[];
  onRefresh: () => void;
  onAnonymise: (subjectId: string, externalId: string) => void;
}): React.ReactElement {
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div>
          <CardTitle>Enrolled subjects</CardTitle>
          <CardDescription>
            {subjects.length === 0
              ? 'No subjects yet — create one above to begin.'
              : `${subjects.length} subject${subjects.length === 1 ? '' : 's'} on file.`}
          </CardDescription>
        </div>
        <Button onClick={onRefresh} variant="outline" size="sm">
          Refresh
        </Button>
      </CardHeader>
      {subjects.length > 0 ? (
        <CardContent>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="border-b border-brand-200 text-left text-xs uppercase tracking-wider text-brand-700">
                <tr>
                  <th className="py-2 pr-4">ID</th>
                  <th className="py-2 pr-4">Age</th>
                  <th className="py-2 pr-4">Sex at birth</th>
                  <th className="py-2 pr-4">Fitzpatrick</th>
                  <th className="py-2 pr-4">Sessions</th>
                  <th className="py-2 pr-4">Pairs</th>
                  <th className="py-2 pr-4">Enrolled</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">Action</th>
                </tr>
              </thead>
              <tbody>
                {subjects.map((s) => {
                  const isAnonymised = s.external_subject_id.startsWith('SUBJ-ANON-');
                  return (
                    <tr key={s.id} className="border-b border-brand-100">
                      <td className="py-2 pr-4 font-mono text-brand-900">
                        {s.external_subject_id}
                      </td>
                      <td className="py-2 pr-4 font-mono text-brand-700">{s.age_years}</td>
                      <td className="py-2 pr-4 font-mono text-xs text-brand-700">
                        {s.sex_assigned_at_birth}
                      </td>
                      <td className="py-2 pr-4 font-mono text-xs text-brand-700">
                        {s.fitzpatrick_scale ?? '—'}
                      </td>
                      <td className="py-2 pr-4 font-mono text-brand-700">
                        {s.session_count}
                      </td>
                      <td className="py-2 pr-4 font-mono text-brand-700">
                        {s.pair_count}
                      </td>
                      <td className="py-2 pr-4 font-mono text-xs text-brand-700">
                        {new Date(s.enrolled_at).toLocaleDateString('en-ZA')}
                      </td>
                      <td className="py-2 pr-4">
                        {isAnonymised || !s.is_active ? (
                          <Badge tone="neutral">ANONYMISED</Badge>
                        ) : (
                          <Badge tone="green">ACTIVE</Badge>
                        )}
                      </td>
                      <td className="py-2 pr-4">
                        {isAnonymised || !s.is_active ? (
                          <span className="text-xs text-brand-500">—</span>
                        ) : (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() =>
                              onAnonymise(s.id, s.external_subject_id)
                            }
                          >
                            Anonymise
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      ) : null}
    </Card>
  );
}

function SessionsList({
  sessions,
}: {
  sessions: StudySessionResponse[];
}): React.ReactElement | null {
  if (sessions.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent sessions</CardTitle>
        <CardDescription>
          Last {sessions.length} sessions across all subjects.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="border-b border-brand-200 text-left text-xs uppercase tracking-wider text-brand-700">
              <tr>
                <th className="py-2 pr-4">Started</th>
                <th className="py-2 pr-4">Subject</th>
                <th className="py-2 pr-4">Posture</th>
                <th className="py-2 pr-4">Time</th>
                <th className="py-2 pr-4">Pairs</th>
                <th className="py-2 pr-4">Locked</th>
                <th className="py-2 pr-4">Ended</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((sessionRow) => (
                <tr key={sessionRow.id} className="border-b border-brand-100">
                  <td className="py-2 pr-4 font-mono text-xs text-brand-700">
                    {new Date(sessionRow.session_started_at).toLocaleString(
                      'en-ZA',
                      { dateStyle: 'short', timeStyle: 'short' },
                    )}
                  </td>
                  <td className="py-2 pr-4 font-mono text-brand-900">
                    {sessionRow.external_subject_id}
                  </td>
                  <td className="py-2 pr-4 font-mono text-xs text-brand-700">
                    {sessionRow.posture}
                  </td>
                  <td className="py-2 pr-4 font-mono text-xs text-brand-700">
                    {sessionRow.time_of_day}
                  </td>
                  <td className="py-2 pr-4 font-mono text-brand-700">
                    {sessionRow.pair_count}
                  </td>
                  <td className="py-2 pr-4 font-mono text-xs text-brand-700">
                    {sessionRow.is_locked ? 'yes' : 'no'}
                  </td>
                  <td className="py-2 pr-4 font-mono text-xs text-brand-700">
                    {sessionRow.ended_at
                      ? new Date(sessionRow.ended_at).toLocaleString('en-ZA', {
                          dateStyle: 'short',
                          timeStyle: 'short',
                        })
                      : 'active'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function Cell({
  label,
  value,
}: {
  label: string;
  value: string;
}): React.ReactElement {
  return (
    <div className="rounded-[var(--radius-control)] border border-brand-100 bg-brand-50 p-3">
      <dt className="text-xs font-semibold uppercase tracking-wider text-brand-700">
        {label}
      </dt>
      <dd className="mt-1 font-mono text-sm text-brand-950">{value}</dd>
    </div>
  );
}
