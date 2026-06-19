'use client';

import { useRouter } from 'next/navigation';
import { useState, useTransition } from 'react';

import {
  CaptureDomain,
  type ResearchCaseCreate,
  type ResearchCaseResponse,
  type RiskClass,
  Sex,
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
import { createResearchCaseAction } from '@/server/research-actions';

const RISK_LABEL: Record<RiskClass, string> = {
  LOW_RISK: 'Low',
  ELEVATED_RISK: 'Elevated',
  HIGH_RISK: 'High',
  VERY_HIGH_RISK: 'Very high',
};

type FormState = {
  age_years: string;
  sex: Sex;
  height_cm: string;
  weight_kg: string;
  waist_cm: string;
  hip_cm: string;
  systolic_bp_mmhg: string;
  diastolic_bp_mmhg: string;
  hba1c_percent: string;
  fasting_glucose_mmol_l: string;
  capture_domain: CaptureDomain;
  notes: string;
};

const EMPTY: FormState = {
  age_years: '',
  sex: Sex.MALE,
  height_cm: '',
  weight_kg: '',
  waist_cm: '',
  hip_cm: '',
  systolic_bp_mmhg: '',
  diastolic_bp_mmhg: '',
  hba1c_percent: '',
  fasting_glucose_mmol_l: '',
  capture_domain: CaptureDomain.CLINICAL_GRADE,
  notes: '',
};

function num(v: string): number | undefined {
  const t = v.trim();
  if (t === '') return undefined;
  const n = Number(t);
  return Number.isFinite(n) ? n : undefined;
}

export function ResearchCaptureForm(): React.ReactElement {
  const router = useRouter();
  const [form, setForm] = useState<FormState>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ResearchCaseResponse | null>(null);
  const [isPending, startTransition] = useTransition();

  const set = (k: keyof FormState) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = (e: React.FormEvent): void => {
    e.preventDefault();
    setError(null);
    const payload: ResearchCaseCreate = {
      age_years: num(form.age_years) ?? 0,
      sex: form.sex,
      height_cm: num(form.height_cm) ?? 0,
      weight_kg: num(form.weight_kg) ?? 0,
      waist_cm: num(form.waist_cm) ?? 0,
      hip_cm: num(form.hip_cm),
      systolic_bp_mmhg: num(form.systolic_bp_mmhg),
      diastolic_bp_mmhg: num(form.diastolic_bp_mmhg),
      hba1c_percent: num(form.hba1c_percent),
      fasting_glucose_mmol_l: num(form.fasting_glucose_mmol_l),
      capture_domain: form.capture_domain,
      notes: form.notes.trim() || undefined,
      safety_triggers: [],
      contextual: [],
    };
    startTransition(async () => {
      const res = await createResearchCaseAction(payload);
      if (res.ok) {
        setResult(res.record);
        setForm((f) => ({ ...EMPTY, capture_domain: f.capture_domain, sex: f.sex }));
        router.refresh();
      } else {
        setError(res.error);
        setResult(null);
      }
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Record a labelled case</CardTitle>
        <CardDescription>
          Obesity and hypertension labels are derived from the measured BMI / BP;
          diabetes from HbA1c or fasting glucose (ADA). Supply a BP reading and a
          glucose marker so all three labels are objective.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error ? (
          <Alert tone="danger" className="mb-4">
            <AlertTitle>Could not record</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

        {result ? (
          <Alert tone="success" className="mb-4">
            <AlertTitle>Recorded — BMI {result.bmi}</AlertTitle>
            <AlertDescription>
              <ul className="mt-1 space-y-0.5 text-sm">
                <li>
                  Obesity <b>{RISK_LABEL[result.obesity_label]}</b> —{' '}
                  {result.label_basis.obesity}
                </li>
                <li>
                  Hypertension <b>{RISK_LABEL[result.hypertension_label]}</b> —{' '}
                  {result.label_basis.hypertension}
                </li>
                <li>
                  Diabetes <b>{RISK_LABEL[result.diabetes_label]}</b> —{' '}
                  {result.label_basis.diabetes}
                </li>
              </ul>
            </AlertDescription>
          </Alert>
        ) : null}

        <form onSubmit={submit} className="space-y-5">
          <fieldset className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Field label="Age (years)" value={form.age_years} onChange={set('age_years')} type="number" required />
            <div className="space-y-1">
              <Label htmlFor="sex">Sex</Label>
              <select
                id="sex"
                value={form.sex}
                onChange={(e) => setForm((f) => ({ ...f, sex: e.target.value as Sex }))}
                className="h-10 w-full rounded-[var(--radius-control)] border border-brand-200 bg-white px-3 text-sm"
              >
                <option value={Sex.MALE}>Male</option>
                <option value={Sex.FEMALE}>Female</option>
                <option value={Sex.OTHER}>Other</option>
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="domain">Measurement</Label>
              <select
                id="domain"
                value={form.capture_domain}
                onChange={(e) =>
                  setForm((f) => ({ ...f, capture_domain: e.target.value as CaptureDomain }))
                }
                className="h-10 w-full rounded-[var(--radius-control)] border border-brand-200 bg-white px-3 text-sm"
              >
                <option value={CaptureDomain.CLINICAL_GRADE}>Clinical instrument</option>
                <option value={CaptureDomain.CHW_TAPE_MEASURE}>CHW tape measure</option>
              </select>
            </div>
          </fieldset>

          <fieldset className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Field label="Height (cm)" value={form.height_cm} onChange={set('height_cm')} type="number" required />
            <Field label="Weight (kg)" value={form.weight_kg} onChange={set('weight_kg')} type="number" required />
            <Field label="Waist (cm)" value={form.waist_cm} onChange={set('waist_cm')} type="number" required />
            <Field label="Hip (cm)" value={form.hip_cm} onChange={set('hip_cm')} type="number" />
          </fieldset>

          <fieldset className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Field label="Systolic BP" value={form.systolic_bp_mmhg} onChange={set('systolic_bp_mmhg')} type="number" />
            <Field label="Diastolic BP" value={form.diastolic_bp_mmhg} onChange={set('diastolic_bp_mmhg')} type="number" />
            <Field label="HbA1c (%)" value={form.hba1c_percent} onChange={set('hba1c_percent')} type="number" />
            <Field label="Fasting glucose (mmol/L)" value={form.fasting_glucose_mmol_l} onChange={set('fasting_glucose_mmol_l')} type="number" />
          </fieldset>

          <div className="space-y-1">
            <Label htmlFor="notes">Notes (optional)</Label>
            <Input id="notes" value={form.notes} onChange={set('notes')} maxLength={2000} />
          </div>

          <Button type="submit" size="lg" disabled={isPending}>
            {isPending ? 'Recording…' : 'Record case'}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function Field({
  label,
  value,
  onChange,
  type = 'text',
  required = false,
}: {
  label: string;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  type?: string;
  required?: boolean;
}): React.ReactElement {
  const id = label.replace(/[^a-z]/gi, '_').toLowerCase();
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} type={type} inputMode="decimal" value={value} onChange={onChange} required={required} />
    </div>
  );
}
