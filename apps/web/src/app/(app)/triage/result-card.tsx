'use client';

import {
  DISEASE_LABELS,
  PlausibilityFlag,
  RISK_CLASSES,
  type PerDiseaseRisk,
  type RiskClass,
  TriageState,
  type TriageAssessmentResponse,
} from '@victus/contracts';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { useDictionary } from '@/i18n/context';
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

/** State → visual tone, used for accents and alerts. */
function stateTone(state: TriageState): 'success' | 'warning' | 'danger' {
  return state === TriageState.RED
    ? 'danger'
    : state === TriageState.YELLOW
      ? 'warning'
      : 'success';
}

const STATE_ACCENT: Record<TriageState, string> = {
  GREEN: 'border-l-emerald-500',
  YELLOW: 'border-l-amber-500',
  RED: 'border-l-rose-600',
};

const STATE_BAR: Record<TriageState, string> = {
  GREEN: 'bg-emerald-500',
  YELLOW: 'bg-amber-500',
  RED: 'bg-rose-600',
};

export function TriageResultCard({
  assessment,
  onRestart,
}: {
  assessment: TriageAssessmentResponse;
  onRestart: () => void;
}): React.ReactElement {
  const tr = useDictionary().triage.result;
  const isFallback = assessment.model_kind.startsWith('rule_based');
  const isOverride = assessment.safety_override_triggered;
  const isDann = assessment.model_kind.includes('dann');
  const isTrained =
    assessment.model_kind.startsWith('trained_torch') && !isOverride;

  return (
    <div className="space-y-6">
      {/* ---- Overall summary banner ---- */}
      <Card className={cn('border-l-4', STATE_ACCENT[assessment.overall_state])}>
        <CardHeader>
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
                Pathway A · Result
              </p>
              <CardTitle className="mt-1 text-2xl">{tr.title}</CardTitle>
              <CardDescription>
                Obesity, hypertension and diabetes are weighted{' '}
                <span className="font-semibold text-brand-900">independently</span>.
                The overall referral state is the worst of the three.
              </CardDescription>
            </div>
            <div className="text-right">
              <p className="text-xs font-semibold uppercase tracking-wider text-brand-700">
                Overall
              </p>
              <div className="mt-1">
                <TriageStateBadge state={assessment.overall_state} />
              </div>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Quick-glance per-disease state pills */}
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            {assessment.per_disease.map((risk) => (
              <div
                key={risk.disease}
                className={cn(
                  'flex items-center justify-between rounded-[var(--radius-control)] border border-brand-100 bg-brand-50 px-3 py-2',
                )}
              >
                <span className="text-sm font-medium text-brand-900">
                  {DISEASE_LABELS[risk.disease]}
                </span>
                <TriageStateBadge state={risk.state} />
              </div>
            ))}
          </div>

          {isOverride ? (
            <Alert tone="danger">
              <AlertTitle>Safety override engaged</AlertTitle>
              <AlertDescription>
                A deterministic red-flag presentation forced an immediate referral
                (overall RED), independent of the per-disease model scores:
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

          <DerivedFeaturesBlock assessment={assessment} />

          {assessment.plausibility_flags.length > 0 ? (
            <Alert tone="warning">
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
                No trained checkpoint is loaded for this environment. Each disease
                uses clinically-grounded WHO / ISH / ADA / Ashwell thresholds with
                conservative evidence weights. Replace with a trained multi-head EDL
                checkpoint by setting{' '}
                <code className="font-mono">VICTUS_TRIAGE_MODEL_PATH</code>.
              </AlertDescription>
            </Alert>
          ) : null}

          {isDann ? (
            <Alert tone="info">
              <AlertTitle>Model: multi-head DANN Evidential Deep Learning</AlertTitle>
              <AlertDescription>
                A shared, domain-invariant feature extractor feeds one Dirichlet
                evidential head per disease, with a gradient-reversal domain
                adversary across{' '}
                <code className="font-mono">CLINICAL_GRADE</code>,{' '}
                <code className="font-mono">CHW_TAPE_MEASURE</code> and{' '}
                <code className="font-mono">SYNTHETIC</code> provenance. Each disease
                is scored — and its uncertainty quantified — independently.
              </AlertDescription>
            </Alert>
          ) : isTrained ? (
            <Alert tone="info">
              <AlertTitle>Model: trained multi-head Evidential Deep Learning</AlertTitle>
              <AlertDescription>
                One Dirichlet evidential head per disease trained on harmonised NCD
                datasets. Per-disease vacuity and aleatoric/epistemic uncertainty are
                surfaced on each card below.
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
            {tr.restart}
          </Button>
        </CardFooter>
      </Card>

      {/* ---- Three independent disease gauges ---- */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {assessment.per_disease.map((risk) => (
          <DiseaseRiskCard key={risk.disease} risk={risk} />
        ))}
      </div>

      <NextActionCard
        nextAction={assessment.next_action}
        state={assessment.overall_state}
      />
    </div>
  );
}

function DiseaseRiskCard({ risk }: { risk: PerDiseaseRisk }): React.ReactElement {
  const topProb = risk.class_probabilities[risk.top_class] ?? 0;
  return (
    <Card className={cn('flex flex-col border-l-4', STATE_ACCENT[risk.state])}>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="text-lg">{DISEASE_LABELS[risk.disease]}</CardTitle>
            <CardDescription>
              {RISK_LABELS[risk.top_class]} · {(topProb * 100).toFixed(0)}% conf · u{' '}
              {risk.uncertainty.vacuity.toFixed(2)}
            </CardDescription>
          </div>
          <TriageStateBadge state={risk.state} />
        </div>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-5">
        <ProbabilityBars risk={risk} />
        <UncertaintyMeters risk={risk} />
        <ContributingFactors risk={risk} />
      </CardContent>
    </Card>
  );
}

function ProbabilityBars({ risk }: { risk: PerDiseaseRisk }): React.ReactElement {
  return (
    <div>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-brand-700">
        Class probabilities
      </h3>
      <ul className="space-y-2">
        {RISK_CLASSES.map((cls) => {
          const p = risk.class_probabilities[cls] ?? 0;
          const pct = p * 100;
          const isTop = cls === risk.top_class;
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
                <span className="font-mono text-brand-700">{pct.toFixed(0)}%</span>
              </div>
              <div
                className="h-2 w-full overflow-hidden rounded-full bg-brand-100"
                role="progressbar"
                aria-valuenow={pct}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`${DISEASE_LABELS[risk.disease]} ${RISK_LABELS[cls]} probability ${pct.toFixed(0)}%`}
              >
                <div
                  style={{ width: `${pct}%` }}
                  className={cn(
                    'h-full transition-all',
                    isTop ? STATE_BAR[risk.state] : 'bg-brand-300',
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

function UncertaintyMeters({ risk }: { risk: PerDiseaseRisk }): React.ReactElement {
  const { vacuity, aleatoric, epistemic, strength } = risk.uncertainty;
  return (
    <div>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-brand-700">
        Uncertainty
      </h3>
      <dl className="grid grid-cols-2 gap-2">
        <MetricCell label="Vacuity (u)" value={vacuity.toFixed(3)} hint="K / S — epistemic proxy" />
        <MetricCell label="Aleatoric" value={aleatoric.toFixed(3)} hint="E[H(p)] — data" />
        <MetricCell label="Epistemic" value={epistemic.toFixed(3)} hint="BALD mutual info" />
        <MetricCell label="Dirichlet S" value={strength.toFixed(2)} hint="Total strength" />
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
    <div className="rounded-[var(--radius-control)] border border-brand-100 bg-brand-50 p-2.5">
      <dt className="text-[0.65rem] font-semibold uppercase tracking-wider text-brand-700">
        {label}
      </dt>
      <dd className="mt-0.5 font-mono text-sm text-brand-950">{value}</dd>
      <p className="mt-0.5 text-[0.65rem] text-brand-600">{hint}</p>
    </div>
  );
}

function ContributingFactors({ risk }: { risk: PerDiseaseRisk }): React.ReactElement {
  return (
    <div className="mt-auto">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-brand-700">
        Contributing factors
      </h3>
      {risk.contributing_factors.length > 0 ? (
        <ul className="space-y-1">
          {risk.contributing_factors.map((factor, i) => (
            <li
              key={`${factor}-${i}`}
              className="flex gap-2 text-xs text-brand-800"
            >
              <span aria-hidden className="mt-1 h-1 w-1 shrink-0 rounded-full bg-brand-400" />
              <span>{factor}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-brand-600">No individual drivers recorded.</p>
      )}
      <p className="mt-3 text-[0.65rem] uppercase tracking-wider text-brand-600">
        Next: <span className="font-semibold text-brand-800">{risk.next_action}</span>
      </p>
    </div>
  );
}

function DerivedFeaturesBlock({
  assessment,
}: {
  assessment: TriageAssessmentResponse;
}): React.ReactElement {
  const d = assessment.derived_features;
  const rows: { label: string; value: string }[] = [
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
    body: 'Vacuity exceeded the YELLOW threshold on at least one disease. Re-collect inputs in case of unit confusion and confirm symptoms with the patient.',
  },
  unit_correction_recheck: {
    title: 'Unit-correction recheck',
    body: 'One or more plausibility flags fired. Re-measure with attention to units before submitting again.',
  },
  clinician_review: {
    title: 'Clinician review',
    body: 'An elevated risk class with sub-threshold confidence — defer to a clinician for review before issuing guidance.',
  },
  clinical_referral: {
    title: 'Clinical referral',
    body: 'High-confidence high-risk classification on at least one disease. Refer to a clinician within 2 weeks.',
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
  const tone = stateTone(state) === 'success' ? 'info' : stateTone(state);
  return (
    <Alert tone={tone}>
      <AlertTitle>{copy.title}</AlertTitle>
      <AlertDescription>{copy.body}</AlertDescription>
    </Alert>
  );
}
