'use client';

import { useActionState, useState } from 'react';

import { AgeRange, EnrollmentRegion, SexAtBirth } from '@victus/contracts';

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
import { enrollAction, type EnrollState } from '@/server/enrollment-actions';

const AGE_RANGES: AgeRange[] = [
  AgeRange.A18_29,
  AgeRange.A30_39,
  AgeRange.A40_49,
  AgeRange.A50_59,
  AgeRange.A60_69,
  AgeRange.A70_PLUS,
];

const SEX_OPTIONS: { value: SexAtBirth; label: string }[] = [
  { value: SexAtBirth.FEMALE, label: 'Female' },
  { value: SexAtBirth.MALE, label: 'Male' },
  { value: SexAtBirth.INTERSEX, label: 'Intersex' },
  { value: SexAtBirth.PREFER_NOT_TO_SAY, label: 'Prefer not to say' },
];

const REGIONS: { value: EnrollmentRegion; label: string }[] = [
  { value: EnrollmentRegion.NG, label: 'Nigeria' },
  { value: EnrollmentRegion.ZW, label: 'Zimbabwe' },
  { value: EnrollmentRegion.ZA, label: 'South Africa' },
  { value: EnrollmentRegion.OTHER, label: 'Other' },
];

const initialState: EnrollState = { ok: false };

export function EnrollForm(): React.ReactElement {
  const [state, formAction, isPending] = useActionState(enrollAction, initialState);
  // The two pathway consents are mandatory — gate the submit on them.
  const [consentTriage, setConsentTriage] = useState(false);
  const [consentToi, setConsentToi] = useState(false);
  const canSubmit = consentTriage && consentToi && !isPending;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Enrolment</CardTitle>
        <CardDescription>
          Before your first check-up we record a few details and your consent.
          This is stored securely; you can request deletion at any time. You must
          be 18 or older to take part.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {state.error ? (
          <Alert tone="danger" className="mb-4">
            <AlertTitle>Could not enrol</AlertTitle>
            <AlertDescription>{state.error}</AlertDescription>
          </Alert>
        ) : null}

        <form action={formAction} className="space-y-6" noValidate>
          {/* Consent */}
          <fieldset className="space-y-2 rounded-[var(--radius-control)] border border-brand-200 p-4">
            <legend className="px-1 text-sm font-semibold text-brand-900">
              Consent
            </legend>
            <label className="flex items-start gap-3 text-sm text-brand-800">
              <input
                type="checkbox"
                name="consent_triage"
                className="mt-1"
                checked={consentTriage}
                onChange={(e) => setConsentTriage(e.target.checked)}
              />
              <span>
                I consent to the <strong>3B-Triage</strong> wellness screening
                (tape-measure + symptom questions). <em>Required.</em>
              </span>
            </label>
            <label className="flex items-start gap-3 text-sm text-brand-800">
              <input
                type="checkbox"
                name="consent_toi_imaging"
                className="mt-1"
                checked={consentToi}
                onChange={(e) => setConsentToi(e.target.checked)}
              />
              <span>
                I consent to the <strong>TOI</strong> contactless face-scan
                vitals estimate. <em>Required.</em>
              </span>
            </label>
            <label className="flex items-start gap-3 text-sm text-brand-800">
              <input type="checkbox" name="consent_research" className="mt-1" />
              <span>
                I agree that my de-identified data may be used for research to
                improve the models. <em>Optional.</em>
              </span>
            </label>
          </fieldset>

          {/* Identity */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <Label htmlFor="full_name">Full name</Label>
              <Input id="full_name" name="full_name" required autoComplete="name" />
            </div>
            <div>
              <Label htmlFor="email">Email</Label>
              <Input id="email" name="email" type="email" required autoComplete="email" />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="patient_id">Patient / client ID</Label>
              <Input id="patient_id" name="patient_id" required />
              <p className="mt-1 text-xs text-brand-600">
                Stored only as a one-way hash — the ID itself is never saved.
              </p>
            </div>
          </div>

          {/* Demographics */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <Label htmlFor="age_range">Age range</Label>
              <select
                id="age_range"
                name="age_range"
                required
                defaultValue=""
                className="mt-1 w-full rounded-[var(--radius-control)] border border-brand-300 bg-white px-3 py-2 text-sm"
              >
                <option value="" disabled>
                  Select…
                </option>
                {AGE_RANGES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="biological_sex">Biological sex</Label>
              <select
                id="biological_sex"
                name="biological_sex"
                required
                defaultValue=""
                className="mt-1 w-full rounded-[var(--radius-control)] border border-brand-300 bg-white px-3 py-2 text-sm"
              >
                <option value="" disabled>
                  Select…
                </option>
                {SEX_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="region">Region</Label>
              <select
                id="region"
                name="region"
                required
                defaultValue=""
                className="mt-1 w-full rounded-[var(--radius-control)] border border-brand-300 bg-white px-3 py-2 text-sm"
              >
                <option value="" disabled>
                  Select…
                </option>
                {REGIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="race_ethnicity">Race / ethnicity (optional)</Label>
              <Input id="race_ethnicity" name="race_ethnicity" />
            </div>
          </div>

          <Button type="submit" size="lg" disabled={!canSubmit} className="w-full">
            {isPending ? 'Enrolling…' : 'Complete enrolment'}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
