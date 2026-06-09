'use client';

import { useState, useTransition } from 'react';

import type {
  SymptomAudit,
  TapeMeasureInputs,
  TriageAssessmentResponse,
} from '@victus/contracts';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

import { AssessmentForm } from './assessment-form';
import { SymptomAuditForm } from './symptom-audit-form';
import { TriageResultCard } from './result-card';
import { assessTriageAction } from '@/server/triage-actions';

type Step = 'inputs' | 'symptoms' | 'result';

export function TriageClient(): React.ReactElement {
  const [step, setStep] = useState<Step>('inputs');
  const [inputs, setInputs] = useState<TapeMeasureInputs | null>(null);
  const [assessment, setAssessment] = useState<TriageAssessmentResponse | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const handleInputs = (next: TapeMeasureInputs): void => {
    setInputs(next);
    setStep('symptoms');
  };

  const handleSymptoms = (symptoms: SymptomAudit): void => {
    if (!inputs) return;
    setServerError(null);
    startTransition(async () => {
      const result = await assessTriageAction({ inputs, symptoms });
      if (result.ok) {
        setAssessment(result.assessment);
        setStep('result');
      } else {
        setServerError(result.error);
      }
    });
  };

  const restart = (): void => {
    setInputs(null);
    setAssessment(null);
    setServerError(null);
    setStep('inputs');
  };

  return (
    <div className="space-y-6">
      <StepIndicator step={step} />
      {serverError ? (
        <Alert tone="danger">
          <AlertTitle>Submission failed</AlertTitle>
          <AlertDescription>{serverError}</AlertDescription>
        </Alert>
      ) : null}

      {step === 'inputs' ? (
        <AssessmentForm onSubmit={handleInputs} isPending={isPending} />
      ) : null}

      {step === 'symptoms' ? (
        <SymptomAuditForm
          onSubmit={handleSymptoms}
          onBack={() => setStep('inputs')}
          isPending={isPending}
        />
      ) : null}

      {step === 'result' && assessment ? (
        <TriageResultCard assessment={assessment} onRestart={restart} />
      ) : null}
    </div>
  );
}

function StepIndicator({ step }: { step: Step }): React.ReactElement {
  const steps: { key: Step; label: string }[] = [
    { key: 'inputs', label: 'Inputs' },
    { key: 'symptoms', label: 'Symptom audit' },
    { key: 'result', label: 'Result' },
  ];
  const activeIndex = steps.findIndex((s) => s.key === step);
  return (
    <ol className="flex items-center gap-2" aria-label="Wizard progress">
      {steps.map((s, i) => {
        const active = i === activeIndex;
        const done = i < activeIndex;
        return (
          <li key={s.key} className="flex items-center gap-2">
            <span
              className={
                'flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold ' +
                (active
                  ? 'bg-brand-600 text-white'
                  : done
                    ? 'bg-brand-200 text-brand-900'
                    : 'bg-brand-50 text-brand-600')
              }
              aria-current={active ? 'step' : undefined}
            >
              {i + 1}
            </span>
            <span
              className={
                'text-sm ' + (active ? 'font-semibold text-brand-900' : 'text-brand-600')
              }
            >
              {s.label}
            </span>
            {i < steps.length - 1 ? <span className="h-px w-6 bg-brand-200" /> : null}
          </li>
        );
      })}
    </ol>
  );
}
