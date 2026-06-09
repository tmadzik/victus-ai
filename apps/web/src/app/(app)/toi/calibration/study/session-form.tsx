'use client';

import { useState, type FormEvent } from 'react';

import {
  POSTURE_LABELS,
  Posture,
  type StartSessionRequest,
  type StudySessionResponse,
  type StudySubjectResponse,
  TIME_OF_DAY_LABELS,
  TimeOfDay,
} from '@victus/contracts';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { startSessionAction } from '@/server/study-actions';

export function SessionForm({
  subjects,
  activeSession,
  onStarted,
}: {
  subjects: StudySubjectResponse[];
  activeSession: StudySessionResponse | null;
  onStarted: (session: StudySessionResponse) => void;
}): React.ReactElement {
  const [subjectId, setSubjectId] = useState<string>(subjects[0]?.id ?? '');
  const [posture, setPosture] = useState<Posture>(Posture.SITTING);
  const [timeOfDay, setTimeOfDay] = useState<TimeOfDay | ''>('');
  const [lux, setLux] = useState('');
  const [tempC, setTempC] = useState('');
  const [humidity, setHumidity] = useState('');
  const [fasted, setFasted] = useState('');
  const [caffeine, setCaffeine] = useState(false);
  const [nicotine, setNicotine] = useState(false);
  const [alcohol, setAlcohol] = useState(false);
  const [lastExercise, setLastExercise] = useState('');
  const [siteLabel, setSiteLabel] = useState('');
  const [notes, setNotes] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isPending, setIsPending] = useState(false);

  const submit = async (e: FormEvent<HTMLFormElement>): Promise<void> => {
    e.preventDefault();
    setError(null);
    if (!subjectId) {
      setError('Pick a subject (or enrol one first).');
      return;
    }
    const numOrNull = (v: string, min: number, max: number): number | null | 'invalid' => {
      const trimmed = v.trim();
      if (trimmed === '') return null;
      const n = Number(trimmed);
      if (!Number.isFinite(n) || n < min || n > max) return 'invalid';
      return n;
    };
    const luxVal = numOrNull(lux, 0, 200_000);
    const tempVal = numOrNull(tempC, -20, 60);
    const humidityVal = numOrNull(humidity, 0, 100);
    const fastedVal = numOrNull(fasted, 0, 72);
    const exVal = numOrNull(lastExercise, 0, 168);
    for (const [name, v] of [
      ['Ambient lux', luxVal],
      ['Temperature', tempVal],
      ['Humidity', humidityVal],
      ['Fasted hours', fastedVal],
      ['Last exercise', exVal],
    ] as const) {
      if (v === 'invalid') {
        setError(`${name} is out of range.`);
        return;
      }
    }
    const payload: StartSessionRequest = {
      study_subject_id: subjectId,
      posture,
      time_of_day: timeOfDay === '' ? null : timeOfDay,
      ambient_lux: luxVal as number | null,
      ambient_temperature_c: tempVal as number | null,
      room_humidity_pct: humidityVal as number | null,
      fasted_hours: fastedVal as number | null,
      caffeine_within_2h: caffeine,
      nicotine_within_2h: nicotine,
      alcohol_within_24h: alcohol,
      last_exercise_hours_ago: exVal as number | null,
      recording_site_label: siteLabel.trim() || null,
      protocol_version: null,
      notes: notes.trim() || null,
    };
    setIsPending(true);
    try {
      const result = await startSessionAction(payload);
      if (!result.ok) {
        setError(result.error);
      } else {
        onStarted(result.value);
        setNotes('');
      }
    } finally {
      setIsPending(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Start a session</CardTitle>
        <CardDescription>
          {activeSession
            ? 'Starting a new session will auto-end your current active session.'
            : 'Once started, the session locks on the first capture so cohort context can’t drift.'}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error ? (
          <Alert tone="danger" className="mb-4">
            <AlertTitle>Cannot start session</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}
        {subjects.length === 0 ? (
          <Alert tone="info">
            <AlertTitle>No subjects enrolled</AlertTitle>
            <AlertDescription>
              Enrol a subject in the panel on the left before starting a session.
            </AlertDescription>
          </Alert>
        ) : (
          <form onSubmit={submit} className="space-y-4" noValidate>
            <div className="space-y-1.5">
              <Label htmlFor="subject">Subject</Label>
              <select
                id="subject"
                value={subjectId}
                onChange={(e) => setSubjectId(e.target.value)}
                className="flex h-10 w-full rounded-[var(--radius-control)] border border-brand-200 bg-white px-3 py-2 text-sm text-brand-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
              >
                {subjects.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.external_subject_id} ({s.age_years} y,{' '}
                    {s.sex_assigned_at_birth.toLowerCase().replaceAll('_', ' ')}
                    {s.fitzpatrick_scale ? `, Fitz ${s.fitzpatrick_scale}` : ''})
                  </option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="posture">Posture</Label>
                <select
                  id="posture"
                  value={posture}
                  onChange={(e) => setPosture(e.target.value as Posture)}
                  className="flex h-10 w-full rounded-[var(--radius-control)] border border-brand-200 bg-white px-3 py-2 text-sm text-brand-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                >
                  {(Object.values(Posture) as Posture[]).map((p) => (
                    <option key={p} value={p}>
                      {POSTURE_LABELS[p]}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="tod">Time of day</Label>
                <select
                  id="tod"
                  value={timeOfDay}
                  onChange={(e) => setTimeOfDay(e.target.value as TimeOfDay | '')}
                  className="flex h-10 w-full rounded-[var(--radius-control)] border border-brand-200 bg-white px-3 py-2 text-sm text-brand-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                >
                  <option value="">Auto-detect from clock</option>
                  {(Object.values(TimeOfDay) as TimeOfDay[]).map((t) => (
                    <option key={t} value={t}>
                      {TIME_OF_DAY_LABELS[t]}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="lux">Ambient lux</Label>
                <Input
                  id="lux"
                  type="number"
                  inputMode="numeric"
                  min={0}
                  step="1"
                  value={lux}
                  onChange={(e) => setLux(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="temp">Temp (°C)</Label>
                <Input
                  id="temp"
                  type="number"
                  inputMode="decimal"
                  step="0.1"
                  value={tempC}
                  onChange={(e) => setTempC(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="humidity">Humidity %</Label>
                <Input
                  id="humidity"
                  type="number"
                  inputMode="numeric"
                  min={0}
                  max={100}
                  step="1"
                  value={humidity}
                  onChange={(e) => setHumidity(e.target.value)}
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="fasted">Fasted hours</Label>
                <Input
                  id="fasted"
                  type="number"
                  inputMode="decimal"
                  min={0}
                  max={72}
                  step="0.5"
                  value={fasted}
                  onChange={(e) => setFasted(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="exercise">Last exercise (hours ago)</Label>
                <Input
                  id="exercise"
                  type="number"
                  inputMode="decimal"
                  min={0}
                  max={168}
                  step="0.5"
                  value={lastExercise}
                  onChange={(e) => setLastExercise(e.target.value)}
                />
              </div>
            </div>
            <fieldset className="space-y-2">
              <legend className="text-sm font-semibold text-brand-900">
                Stimulant / depressant covariates
              </legend>
              <CheckboxRow
                label="Caffeine in the last 2 hours"
                checked={caffeine}
                onChange={setCaffeine}
              />
              <CheckboxRow
                label="Nicotine in the last 2 hours"
                checked={nicotine}
                onChange={setNicotine}
              />
              <CheckboxRow
                label="Alcohol in the last 24 hours"
                checked={alcohol}
                onChange={setAlcohol}
              />
            </fieldset>
            <div className="space-y-1.5">
              <Label htmlFor="site">Recording site label (optional)</Label>
              <Input
                id="site"
                type="text"
                maxLength={120}
                value={siteLabel}
                onChange={(e) => setSiteLabel(e.target.value)}
                placeholder="e.g. Cape Town CHW Clinic Room A"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="notes">Notes (optional)</Label>
              <Input
                id="notes"
                type="text"
                maxLength={2000}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Anything material to reproducibility."
              />
            </div>
            <div className="flex justify-end">
              <Button type="submit" disabled={isPending}>
                {isPending ? 'Starting…' : 'Start session'}
              </Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

function CheckboxRow({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (on: boolean) => void;
}): React.ReactElement {
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-[var(--radius-control)] border border-brand-100 p-2.5 hover:border-brand-300">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 cursor-pointer rounded border-brand-300 text-brand-600 focus-visible:ring-2 focus-visible:ring-brand-500"
      />
      <span className="text-sm leading-snug text-brand-900">{label}</span>
    </label>
  );
}
