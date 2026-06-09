'use client';

import { useCallback, useState, useTransition } from 'react';

import type { RppgFrame, ToiAssessmentResponse } from '@victus/contracts';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

import { CaptureStep } from './capture-step';
import { ConsentStep } from './consent-step';
import { ResultCard } from './result-card';
import { assessToiAction } from '@/server/toi-actions';

type Step = 'consent' | 'capture' | 'processing' | 'result';

export interface CompletedCapture {
  samples: RppgFrame[];
  sampleRateHz: number;
  durationS: number;
  motionScore: number;
  lightingScore: number;
  facePresenceRatio: number;
}

export function ToiClient(): React.ReactElement {
  const [step, setStep] = useState<Step>('consent');
  const [error, setError] = useState<string | null>(null);
  const [assessment, setAssessment] = useState<ToiAssessmentResponse | null>(null);
  const [isPending, startTransition] = useTransition();

  const handleConsent = useCallback((): void => {
    setError(null);
    setStep('capture');
  }, []);

  const handleCaptureComplete = useCallback(
    (capture: CompletedCapture): void => {
      setError(null);
      setStep('processing');
      startTransition(async () => {
        const result = await assessToiAction({
          frames: capture.samples,
          sample_rate_hz: capture.sampleRateHz,
          duration_s: capture.durationS,
          motion_score: capture.motionScore,
          lighting_score: capture.lightingScore,
          face_presence_ratio: capture.facePresenceRatio,
        });
        if (result.ok) {
          setAssessment(result.assessment);
          setStep('result');
        } else {
          setError(result.error);
          setStep('capture');
        }
      });
    },
    [],
  );

  const restart = useCallback((): void => {
    setAssessment(null);
    setError(null);
    setStep('consent');
  }, []);

  return (
    <div className="space-y-6">
      <StepIndicator step={step} />

      {error ? (
        <Alert tone="danger">
          <AlertTitle>Capture failed</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {step === 'consent' ? <ConsentStep onContinue={handleConsent} /> : null}

      {step === 'capture' ? (
        <CaptureStep onCaptureComplete={handleCaptureComplete} disabled={isPending} />
      ) : null}

      {step === 'processing' ? (
        <Alert tone="info">
          <AlertTitle>Analysing signal…</AlertTitle>
          <AlertDescription>
            Server-side CHROM and POS pipelines are running on the captured
            frame series. This typically takes 1–3 seconds.
          </AlertDescription>
        </Alert>
      ) : null}

      {step === 'result' && assessment ? (
        <ResultCard assessment={assessment} onRestart={restart} />
      ) : null}
    </div>
  );
}

function StepIndicator({ step }: { step: Step }): React.ReactElement {
  const steps: { key: Step; label: string }[] = [
    { key: 'consent', label: 'Setup' },
    { key: 'capture', label: 'Capture' },
    { key: 'processing', label: 'Analyse' },
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
