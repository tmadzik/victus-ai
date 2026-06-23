'use client';

import { useState } from 'react';

import {
  CONTEXTUAL_SYMPTOM_KEYS,
  SAFETY_OVERRIDE_SYMPTOM_KEYS,
  type ContextualSymptomKey,
  type SafetyOverrideSymptomKey,
  type SymptomAudit,
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
import { useDictionary } from '@/i18n/context';

const SAFETY_LABELS: Record<SafetyOverrideSymptomKey, string> = {
  polydipsia_unquenchable_thirst:
    'Persistent, unquenchable thirst (polydipsia)',
  blurred_vision_progressive: 'Progressively blurred or worsening vision',
  non_healing_foot_sore:
    'A foot sore or ulcer that has not healed in 2+ weeks',
  chest_pain_radiating:
    'Chest pain that radiates to the arm, jaw, or back',
  severe_headache_with_visual_change:
    'Severe headache accompanied by visual changes',
  polyuria_nocturia_severe:
    'Frequent urination (incl. waking at night to urinate)',
  unexplained_weight_loss_recent:
    'Unexplained weight loss in the past 1–3 months',
};

const CONTEXTUAL_LABELS: Record<ContextualSymptomKey, string> = {
  fatigue_persistent: 'Persistent fatigue beyond what activity would explain',
  family_history_diabetes: 'First-degree relative with diabetes',
  family_history_hypertension: 'First-degree relative with hypertension',
  smoker_current: 'Currently smokes tobacco (or vapes nicotine)',
  physical_activity_low: 'Less than 150 minutes of moderate activity per week',
};

export function SymptomAuditForm({
  onSubmit,
  onBack,
  isPending,
}: {
  onSubmit: (symptoms: SymptomAudit) => void;
  onBack: () => void;
  isPending: boolean;
}): React.ReactElement {
  const t = useDictionary().triage.symptoms;
  const [safety, setSafety] = useState<Set<SafetyOverrideSymptomKey>>(new Set());
  const [contextual, setContextual] = useState<Set<ContextualSymptomKey>>(new Set());

  const toggleSafety = (key: SafetyOverrideSymptomKey, on: boolean) =>
    setSafety((prev) => {
      const next = new Set(prev);
      if (on) next.add(key);
      else next.delete(key);
      return next;
    });

  const toggleContextual = (key: ContextualSymptomKey, on: boolean) =>
    setContextual((prev) => {
      const next = new Set(prev);
      if (on) next.add(key);
      else next.delete(key);
      return next;
    });

  const submit = (): void => {
    onSubmit({
      safety_triggers: [...safety],
      contextual: [...contextual],
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t.title}</CardTitle>
        <CardDescription>
          Any item in the first group triggers an immediate clinical referral
          regardless of the network&apos;s prediction. Be honest: this is the
          deterministic safety layer.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {safety.size > 0 ? (
          <Alert tone="danger">
            <AlertTitle>{t.triggersRed}</AlertTitle>
            <AlertDescription>
              {safety.size} red-flag symptom{safety.size === 1 ? '' : 's'} selected.
              The clinical-referral pathway will engage on submit.
            </AlertDescription>
          </Alert>
        ) : null}

        <fieldset className="space-y-3">
          <legend className="text-sm font-semibold text-brand-900">
            Red-flag symptoms
          </legend>
          {SAFETY_OVERRIDE_SYMPTOM_KEYS.map((key) => (
            <CheckboxRow
              key={key}
              label={SAFETY_LABELS[key]}
              checked={safety.has(key)}
              onChange={(on) => toggleSafety(key, on)}
              danger
            />
          ))}
        </fieldset>

        <fieldset className="space-y-3">
          <legend className="text-sm font-semibold text-brand-900">
            Contextual risk factors
          </legend>
          {CONTEXTUAL_SYMPTOM_KEYS.map((key) => (
            <CheckboxRow
              key={key}
              label={CONTEXTUAL_LABELS[key]}
              checked={contextual.has(key)}
              onChange={(on) => toggleContextual(key, on)}
            />
          ))}
        </fieldset>

        <div className="flex justify-between pt-2">
          <Button variant="outline" onClick={onBack} disabled={isPending}>
            {t.back}
          </Button>
          <Button onClick={submit} size="lg" disabled={isPending}>
            {isPending ? t.submitting : t.run}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function CheckboxRow({
  label,
  checked,
  onChange,
  danger,
}: {
  label: string;
  checked: boolean;
  onChange: (on: boolean) => void;
  danger?: boolean;
}): React.ReactElement {
  return (
    <label
      className={
        'flex cursor-pointer items-start gap-3 rounded-[var(--radius-control)] border p-3 transition-colors ' +
        (danger
          ? 'border-brand-100 hover:border-[color:var(--color-state-red-ring)]/60'
          : 'border-brand-100 hover:border-brand-300')
      }
    >
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
