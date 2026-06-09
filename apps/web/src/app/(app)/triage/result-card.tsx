'use client';

import {
  PlausibilityFlag,
  RISK_CLASSES,
  type RiskClass,
  TriageState,
  type TriageAssessmentResponse,
} from '@victus/contracts';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { TriageStateBadge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { cn } from '@/lib/utils';

const RISK_LABELS: Record<RiskClass, string> = {
  LOW_RISK: 'Low risk',
  ELEVATED_RISK: 'Elevated',
  HIGH_RISK: 'High',
  VERY_HIGH_RISK: 'Very high',
};

const FLAG_LABELS: Record<PlausibilityFlag, string> = {
  BMI_OUT_OF_RANGE: 'BMI is outside the plausible range (10–70) — please re-measure.',
  WAIST_GT_HEIGHT: 'Waist measurement exceeds height — physically impossible.',
  WAIST_TOO_SMALL: 'Waist-to-height ratio is below 0.30 — recheck the measurement.',
  BP_INVERTED: 'Systolic must be greater than diastolic — recheck the cuff reading.',
  BP_EXTREME: 'Blood pressure reading suggests a hypertensive crisis — verify and refer.',
  POSSIBLE_UNIT_CONFUSION_HEIGHT:
    'Height appears very low — confirm the unit (cm, not metres).',
  POSSIBLE_UNIT_CONFUSION_WEIGHT:
    'Weight appears very high — confirm the unit (kg, not pounds).',
};

export function TriageResultCard({
  assessment,
  onRestart,
}: {
  assessment: TriageAssessmentResponse;
  onRestart: () => void;
}): React.ReactElement {
  const stateTone =
    assessment.state === TriageState.RED
      ? 'danger'
      : assessment.state === TriageState.YELLOW
        ? 'warning'
        : 'success';

  const isFallback = assessment.model_kind.startsWith('rule_based');
  const isOverride = assessment.safety_override_triggered;
  const isDann = assessment.model_kind === 'trained_torch_dann_v1';
  const isTrained =
    assessment.model_kind.startsWith('trained_torch') && !isOverride;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
                Pathway A · Result
              </p>
              <CardTitle className="mt-1 text-2xl">
                {RISK_LABELS[assessment.top_class]}
              </CardTitle>
              <CardDescription>
                Top class confidence{' '}
                <span className="font-semibold text-brand-900">
                  {((assessment.class_probabilities[assessment.top_class] ?? 0) * 100).toFixed(1)}%
                </span>{' '}
                · vacuity{' '}
                <span className="font-semibold text-brand-900">
                  {assessment.uncertainty.vacuity.toFixed(3)}
                </span>
              </CardDescription>
            </div>
            <TriageStateBadge state={assessment.state} />
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {isOverride ? (
            <Alert tone="danger">
              <AlertTitle>Safety override engaged</AlertTitle>
              <AlertDescription>
                The neural network was bypassed because the symptom audit
                surfaced a deterministic red-flag presentation:
                <ul className="mt-2 list-disc pl-5">
                  {assessment.override_reasons.map((r) => (
                    <li key={r} className="text-sm">
                      <code className="font-mono">{r}</code>
                    </li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          ) : null}

          <ProbabilityBars assessment={assessment} />

          <UncertaintyMeters assessment={assessment} />

          <DerivedFeaturesBlock assessment={assessment} />

          {assessment.plausibility_flags.length > 0 ? (
            <Alert tone={stateTone === 'success' ? 'warning' : stateTone}>
              <AlertTitle>Plausibility checks</AlertTitle>
              <AlertDescription>
                <ul className="space-y-1">
                  {assessment.plausibility_flags.map((f) => (
                    <li key={f} className="text-sm">
                      {FLAG_LABELS[f]}
                    </li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          ) : null}

          {isFallback && !isOverride ? (
            <Alert tone="info">
              <AlertTitle>Model: rule-based fallback</AlertTitle>
              <AlertDescription>
                No trained checkpoint is loaded for this environment. The result
                uses clinically-grounded WHO / ISH thresholds with conservative
                evidence weights. Replace with a trained EDL checkpoint by
                setting <code className="font-mono">VICTUS_TRIAGE_MODEL_PATH</code>.
              </AlertDescription>
            </Alert>
          ) : null}

          {isDann ? (
            <Alert tone="info">
              <AlertTitle>Model: DANN-augmented Evidential Deep Learning</AlertTitle>
              <AlertDescription>
                Shared feature extractor with an EDL Dirichlet task head and a
                gradient-reversal domain adversary. Features are explicitly
                trained to be invariant across{' '}
                <code className="font-mono">CLINICAL_GRADE</code>,{' '}
                <code className="font-mono">CHW_TAPE_MEASURE</code>, and{' '}
                <code className="font-mono">SYNTHETIC</code> measurement
                provenance, so tape-measure inputs collected in the field
                behave the same as clinical-grade inputs.
              </AlertDescription>
            </Alert>
          ) : isTrained ? (
            <Alert tone="info">
              <AlertTitle>Model: trained Evidential Deep Learning</AlertTitle>
              <AlertDescription>
                Dirichlet evidential head trained on harmonised NCD datasets.
                Vacuity and aleatoric/epistemic uncertainty are surfaced above.
              </AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
        <CardFooter className="flex justify-between">
          <p className="text-xs text-brand-600">
            Assessment <code className="font-mono">{assessment.id.slice(0, 8)}…</code>{' '}
            recorded at{' '}
            {new Date(assessment.created_at).toLocaleString('en-ZA', {
              dateStyle: 'medium',
              timeStyle: 'short',
            })}
          </p>
          <Button onClick={onRestart} variant="outline" size="sm">
            Start a new assessment
          </Button>
        </CardFooter>
      </Card>

      <NextActionCard nextAction={assessment.next_action} state={assessment.state} />
    </div>
  );
}

function ProbabilityBars({
  assessment,
}: {
  assessment: TriageAssessmentResponse;
}): React.ReactElement {
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold text-brand-900">Class probabilities</h3>
      <ul className="space-y-2">
        {RISK_CLASSES.map((cls) => {
          const p = assessment.class_probabilities[cls] ?? 0;
          const pct = p * 100;
          const isTop = cls === assessment.top_class;
          return (
            <li key={cls}>
              <div className="mb-1 flex items-center justify-between text-xs">
                <span
                  className={cn(
                    'font-medium',
                    isTop ? 'text-brand-900' : 'text-brand-700',
                  )}
                >
                  {RISK_LABELS[cls]}
                </span>
                <span className="font-mono text-brand-700">
                  {pct.toFixed(1)}%
                </span>
              </div>
              <div
                className="h-2 w-full overflow-hidden rounded-full bg-brand-100"
                role="progressbar"
                aria-valuenow={pct}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`${RISK_LABELS[cls]} probability ${pct.toFixed(1)}%`}
              >
                <div
                  style={{ width: `${pct}%` }}
                  className={cn(
                    'h-full transition-all',
                    isTop ? 'bg-brand-600' : 'bg-brand-300',
                  )}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function UncertaintyMeters({
  assessment,
}: {
  assessment: TriageAssessmentResponse;
}): React.ReactElement {
  const { vacuity, aleatoric, epistemic, strength } = assessment.uncertainty;
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold text-brand-900">
        Uncertainty decomposition
      </h3>
      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <MetricCell label="Vacuity (u)" value={vacuity.toFixed(3)} hint="K / S — epistemic proxy" />
        <MetricCell
          label="Aleatoric"
          value={aleatoric.toFixed(3)}
          hint="E[H(p)] — data uncertainty"
        />
        <MetricCell
          label="Epistemic (BALD)"
          value={epistemic.toFixed(3)}
          hint="H[E[p]] − E[H(p)]"
        />
        <MetricCell
          label="Dirichlet S"
          value={strength.toFixed(2)}
          hint="Total Dirichlet strength"
        />
      </dl>
    </div>
  );
}

function MetricCell({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}): React.ReactElement {
  return (
    <div className="rounded-[var(--radius-control)] border border-brand-100 bg-brand-50 p-3">
      <dt className="text-xs font-semibold uppercase tracking-wider text-brand-700">
        {label}
      </dt>
      <dd className="mt-1 font-mono text-base text-brand-950">{value}</dd>
      <p className="mt-1 text-xs text-brand-600">{hint}</p>
    </div>
  );
}

function DerivedFeaturesBlock({
  assessment,
}: {
  assessment: TriageAssessmentResponse;
}): React.ReactElement {
  const d = assessment.derived_features;
  const rows: { label: string; value: string; note?: string }[] = [
    { label: 'BMI', value: d.bmi !== null ? d.bmi.toFixed(1) : '—' },
    { label: 'Waist / Height', value: d.whtr !== null ? d.whtr.toFixed(3) : '—' },
    { label: 'Waist / Hip', value: d.whr !== null ? d.whr.toFixed(3) : '—' },
    {
      label: 'Pulse pressure',
      value:
        d.pulse_pressure_mmhg !== null
          ? `${d.pulse_pressure_mmhg.toFixed(0)} mmHg`
          : '—',
    },
  ];
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold text-brand-900">Derived features</h3>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {rows.map((r) => (
          <div
            key={r.label}
            className="rounded-[var(--radius-control)] border border-brand-100 p-3"
          >
            <dt className="text-xs font-semibold uppercase tracking-wider text-brand-700">
              {r.label}
            </dt>
            <dd className="mt-1 font-mono text-sm text-brand-950">{r.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

const NEXT_ACTION_COPY: Record<string, { title: string; body: string }> = {
  routine_followup: {
    title: 'Routine follow-up',
    body: 'Re-screen in 12 months unless clinical context changes. Reinforce lifestyle guidance.',
  },
  symptom_audit_fallback: {
    title: 'Re-run with symptom audit',
    body: 'Vacuity exceeded the YELLOW threshold. Re-collect inputs in case of unit confusion and confirm symptoms with the patient.',
  },
  unit_correction_recheck: {
    title: 'Unit-correction recheck',
    body: 'One or more plausibility flags fired. Re-measure with attention to units before submitting again.',
  },
  clinician_review: {
    title: 'Clinician review',
    body: 'Elevated risk class with sub-threshold confidence — defer to a clinician for review before issuing guidance.',
  },
  clinical_referral: {
    title: 'Clinical referral',
    body: 'High-confidence high-risk classification. Refer to a clinician within 2 weeks.',
  },
  immediate_clinical_referral: {
    title: 'Immediate referral',
    body: 'Safety override engaged. Refer to a clinician now and do not delay for the network result.',
  },
};

function NextActionCard({
  nextAction,
  state,
}: {
  nextAction: string;
  state: TriageState;
}): React.ReactElement {
  const copy = NEXT_ACTION_COPY[nextAction] ?? {
    title: 'Next action',
    body: nextAction,
  };
  const tone =
    state === TriageState.RED ? 'danger' : state === TriageState.YELLOW ? 'warning' : 'info';
  return (
    <Alert tone={tone}>
      <AlertTitle>{copy.title}</AlertTitle>
      <AlertDescription>{copy.body}</AlertDescription>
    </Alert>
  );
}
