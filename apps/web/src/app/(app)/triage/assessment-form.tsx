'use client';

import { useState, type FormEvent } from 'react';

import {
  Sex,
  type TapeMeasureInputs,
  TapeMeasureInputsSchema,
} from '@victus/contracts';

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
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { useDictionary } from '@/i18n/context';

interface RawForm {
  height_cm: string;
  weight_kg: string;
  waist_cm: string;
  hip_cm: string;
  age_years: string;
  sex: Sex | '';
  systolic_bp_mmhg: string;
  diastolic_bp_mmhg: string;
}

const EMPTY: RawForm = {
  height_cm: '',
  weight_kg: '',
  waist_cm: '',
  hip_cm: '',
  age_years: '',
  sex: '',
  systolic_bp_mmhg: '',
  diastolic_bp_mmhg: '',
};

function parseRaw(raw: RawForm):
  | { ok: true; inputs: TapeMeasureInputs }
  | { ok: false; fieldErrors: Partial<Record<keyof RawForm, string>> } {
  const fieldErrors: Partial<Record<keyof RawForm, string>> = {};
  const num = (v: string): number | undefined => {
    if (v.trim() === '') return undefined;
    const n = Number(v);
    return Number.isFinite(n) ? n : Number.NaN;
  };

  const candidate = {
    height_cm: num(raw.height_cm),
    weight_kg: num(raw.weight_kg),
    waist_cm: num(raw.waist_cm),
    hip_cm: num(raw.hip_cm),
    age_years: num(raw.age_years),
    sex: raw.sex === '' ? undefined : raw.sex,
    systolic_bp_mmhg: num(raw.systolic_bp_mmhg),
    diastolic_bp_mmhg: num(raw.diastolic_bp_mmhg),
  };

  // Strip undefineds before validating so optional checks behave correctly.
  const filtered: Record<string, unknown> = {};
  (Object.keys(candidate) as (keyof typeof candidate)[]).forEach((k) => {
    if (candidate[k] !== undefined) filtered[k] = candidate[k];
  });

  const parsed = TapeMeasureInputsSchema.safeParse(filtered);
  if (!parsed.success) {
    parsed.error.issues.forEach((issue) => {
      const path = issue.path[0];
      if (typeof path === 'string') {
        fieldErrors[path as keyof RawForm] = issue.message;
      }
    });
    return { ok: false, fieldErrors };
  }
  return { ok: true, inputs: parsed.data };
}

export function AssessmentForm({
  onSubmit,
  isPending,
}: {
  onSubmit: (inputs: TapeMeasureInputs) => void;
  isPending: boolean;
}): React.ReactElement {
  const dict = useDictionary();
  const t = dict.triage.form;
  const [raw, setRaw] = useState<RawForm>(EMPTY);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<keyof RawForm, string>>>(
    {},
  );
  const [formError, setFormError] = useState<string | null>(null);

  const update = (key: keyof RawForm) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setRaw((r) => ({ ...r, [key]: e.target.value }));

  const handleSubmit = (e: FormEvent<HTMLFormElement>): void => {
    e.preventDefault();
    const result = parseRaw(raw);
    if (!result.ok) {
      setFieldErrors(result.fieldErrors);
      setFormError(t.fixFields);
      return;
    }
    setFieldErrors({});
    setFormError(null);
    onSubmit(result.inputs);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t.title}</CardTitle>
        <CardDescription>{t.description}</CardDescription>
      </CardHeader>
      <CardContent>
        {formError ? (
          <Alert tone="danger" className="mb-4">
            <AlertTitle>{t.needsAttention}</AlertTitle>
            <AlertDescription>{formError}</AlertDescription>
          </Alert>
        ) : null}

        <form onSubmit={handleSubmit} className="grid gap-4 sm:grid-cols-2" noValidate>
          <Field label={t.height} id="height_cm" error={fieldErrors.height_cm}>
            <Input
              id="height_cm"
              type="number"
              inputMode="decimal"
              step="0.1"
              min={50}
              max={250}
              required
              value={raw.height_cm}
              onChange={update('height_cm')}
            />
          </Field>
          <Field label={t.weight} id="weight_kg" error={fieldErrors.weight_kg}>
            <Input
              id="weight_kg"
              type="number"
              inputMode="decimal"
              step="0.1"
              min={5}
              max={400}
              required
              value={raw.weight_kg}
              onChange={update('weight_kg')}
            />
          </Field>
          <Field label={t.waist} id="waist_cm" error={fieldErrors.waist_cm}>
            <Input
              id="waist_cm"
              type="number"
              inputMode="decimal"
              step="0.1"
              min={30}
              max={250}
              required
              value={raw.waist_cm}
              onChange={update('waist_cm')}
            />
          </Field>
          <Field label={t.hip} id="hip_cm" error={fieldErrors.hip_cm}>
            <Input
              id="hip_cm"
              type="number"
              inputMode="decimal"
              step="0.1"
              min={40}
              max={250}
              value={raw.hip_cm}
              onChange={update('hip_cm')}
            />
          </Field>
          <Field label={t.age} id="age_years" error={fieldErrors.age_years}>
            <Input
              id="age_years"
              type="number"
              inputMode="numeric"
              step="1"
              min={1}
              max={120}
              required
              value={raw.age_years}
              onChange={update('age_years')}
            />
          </Field>
          <Field label={t.sex} id="sex" error={fieldErrors.sex}>
            <select
              id="sex"
              required
              value={raw.sex}
              onChange={update('sex')}
              className="flex h-10 w-full rounded-[var(--radius-control)] border border-brand-200 bg-white px-3 py-2 text-sm text-brand-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
            >
              <option value="">{t.select}</option>
              <option value={Sex.MALE}>{t.male}</option>
              <option value={Sex.FEMALE}>{t.female}</option>
              <option value={Sex.OTHER}>{t.other}</option>
            </select>
          </Field>
          <Field
            label={t.systolic}
            id="systolic_bp_mmhg"
            error={fieldErrors.systolic_bp_mmhg}
          >
            <Input
              id="systolic_bp_mmhg"
              type="number"
              inputMode="numeric"
              step="1"
              min={50}
              max={260}
              value={raw.systolic_bp_mmhg}
              onChange={update('systolic_bp_mmhg')}
            />
          </Field>
          <Field
            label={t.diastolic}
            id="diastolic_bp_mmhg"
            error={fieldErrors.diastolic_bp_mmhg}
          >
            <Input
              id="diastolic_bp_mmhg"
              type="number"
              inputMode="numeric"
              step="1"
              min={30}
              max={160}
              value={raw.diastolic_bp_mmhg}
              onChange={update('diastolic_bp_mmhg')}
            />
          </Field>

          <div className="sm:col-span-2 mt-2 flex justify-end">
            <Button type="submit" size="lg" disabled={isPending}>
              {isPending ? t.working : t.continue}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function Field({
  label,
  id,
  error,
  children,
}: {
  label: string;
  id: string;
  error?: string;
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error ? (
        <p className="text-xs text-[color:var(--color-state-red-fg)]">{error}</p>
      ) : null}
    </div>
  );
}
