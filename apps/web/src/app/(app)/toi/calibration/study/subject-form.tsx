'use client';

import { useState, type FormEvent } from 'react';

import {
  FitzpatrickScale,
  SexAtBirth,
  type StudySubjectResponse,
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
import { createSubjectAction } from '@/server/study-actions';

export function SubjectForm({
  onCreated,
}: {
  onCreated: (subject: StudySubjectResponse) => void;
}): React.ReactElement {
  const [externalId, setExternalId] = useState('');
  const [age, setAge] = useState('');
  const [sex, setSex] = useState<SexAtBirth>(SexAtBirth.PREFER_NOT_TO_SAY);
  const [fitz, setFitz] = useState<FitzpatrickScale | ''>('');
  const [height, setHeight] = useState('');
  const [weight, setWeight] = useState('');
  const [historySummary, setHistorySummary] = useState('');
  const [consentVersion, setConsentVersion] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isPending, setIsPending] = useState(false);

  const submit = async (e: FormEvent<HTMLFormElement>): Promise<void> => {
    e.preventDefault();
    setError(null);

    const ageNum = Number(age);
    if (!Number.isInteger(ageNum) || ageNum < 0 || ageNum > 130) {
      setError('Age must be an integer between 0 and 130.');
      return;
    }
    const heightNum = height.trim() === '' ? null : Number(height);
    if (heightNum !== null && (!Number.isFinite(heightNum) || heightNum <= 0 || heightNum > 250)) {
      setError('Height must be > 0 and ≤ 250 cm, or blank.');
      return;
    }
    const weightNum = weight.trim() === '' ? null : Number(weight);
    if (weightNum !== null && (!Number.isFinite(weightNum) || weightNum <= 0 || weightNum > 400)) {
      setError('Weight must be > 0 and ≤ 400 kg, or blank.');
      return;
    }

    setIsPending(true);
    try {
      const result = await createSubjectAction({
        external_subject_id: externalId.trim(),
        age_years: ageNum,
        sex_assigned_at_birth: sex,
        fitzpatrick_scale: fitz === '' ? null : fitz,
        height_cm: heightNum,
        weight_kg: weightNum,
        medical_history_summary: historySummary.trim() || null,
        consent_protocol_version: consentVersion.trim() || null,
      });
      if (!result.ok) {
        setError(result.error);
      } else {
        onCreated(result.value);
        setExternalId('');
        setAge('');
        setHeight('');
        setWeight('');
        setHistorySummary('');
      }
    } finally {
      setIsPending(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Enrol a new subject</CardTitle>
        <CardDescription>
          Anonymous identifier — your bookkeeping label, no PII. The same
          identifier can be re-used in future studies; uniqueness is per
          researcher.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error ? (
          <Alert tone="danger" className="mb-4">
            <AlertTitle>Cannot enrol</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}
        <form onSubmit={submit} className="space-y-4" noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="ext-id">Subject ID</Label>
            <Input
              id="ext-id"
              type="text"
              required
              maxLength={64}
              pattern="^[A-Za-z0-9_\-:.]+$"
              value={externalId}
              onChange={(e) => setExternalId(e.target.value)}
              placeholder="e.g. S001, SUBJ-2026-001"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="age">Age (years)</Label>
              <Input
                id="age"
                type="number"
                inputMode="numeric"
                required
                min={0}
                max={130}
                step="1"
                value={age}
                onChange={(e) => setAge(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="sex">Sex assigned at birth</Label>
              <select
                id="sex"
                required
                value={sex}
                onChange={(e) => setSex(e.target.value as SexAtBirth)}
                className="flex h-10 w-full rounded-[var(--radius-control)] border border-brand-200 bg-white px-3 py-2 text-sm text-brand-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
              >
                {(Object.values(SexAtBirth) as SexAtBirth[]).map((s) => (
                  <option key={s} value={s}>
                    {s.replaceAll('_', ' ')}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="fitz">Fitzpatrick</Label>
              <select
                id="fitz"
                value={fitz}
                onChange={(e) => setFitz(e.target.value as FitzpatrickScale | '')}
                className="flex h-10 w-full rounded-[var(--radius-control)] border border-brand-200 bg-white px-3 py-2 text-sm text-brand-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
              >
                <option value="">—</option>
                {(['I', 'II', 'III', 'IV', 'V', 'VI'] as FitzpatrickScale[]).map(
                  (f) => (
                    <option key={f} value={f}>
                      Type {f}
                    </option>
                  ),
                )}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="height">Height (cm)</Label>
              <Input
                id="height"
                type="number"
                inputMode="decimal"
                min={1}
                max={250}
                step="0.1"
                value={height}
                onChange={(e) => setHeight(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="weight">Weight (kg)</Label>
              <Input
                id="weight"
                type="number"
                inputMode="decimal"
                min={1}
                max={400}
                step="0.1"
                value={weight}
                onChange={(e) => setWeight(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="history">Medical history summary (optional)</Label>
            <Input
              id="history"
              type="text"
              maxLength={2000}
              value={historySummary}
              onChange={(e) => setHistorySummary(e.target.value)}
              placeholder="Brief, IRB-approved notes only."
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="consent">Consent protocol version (optional)</Label>
            <Input
              id="consent"
              type="text"
              maxLength={64}
              value={consentVersion}
              onChange={(e) => setConsentVersion(e.target.value)}
              placeholder="Defaults to VICTUS-IRB-CONSENT-V1"
            />
          </div>
          <div className="flex justify-end">
            <Button type="submit" disabled={isPending}>
              {isPending ? 'Enrolling…' : 'Enrol subject'}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
