'use client';

import type {
  BiomarkerEstimate,
  ToiAssessmentResponse,
} from '@victus/contracts';
import { ToiQuality } from '@victus/contracts';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useDictionary, useFormatLocale } from '@/i18n/context';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';

const QUALITY_TONE: Record<
  ToiQuality,
  { tone: 'green' | 'yellow' | 'red'; label: string }
> = {
  GOOD: { tone: 'green', label: 'Signal good' },
  DEGRADED: { tone: 'yellow', label: 'Signal degraded' },
  POOR: { tone: 'red', label: 'Signal too poor' },
};

const BIOMARKER_LABEL: Record<string, string> = {
  heart_rate: 'Heart Rate',
  respiratory_rate: 'Respiratory Rate',
  hrv_rmssd: 'HRV (RMSSD)',
  hrv_sdnn: 'HRV (SDNN)',
  stress_index: 'Stress Index',
};

export function ResultCard({
  assessment,
  onRestart,
}: {
  assessment: ToiAssessmentResponse;
  onRestart: () => void;
}): React.ReactElement {
  const r = useDictionary().toi.result;
  const fmtLoc = useFormatLocale();
  const quality = QUALITY_TONE[assessment.quality];
  const sq = assessment.signal_quality;

  return (
    <div className="space-y-6 print-summary">
      {/* Print-only document header (hidden on screen). */}
      <div className="print-only mb-4 border-b border-brand-200 pb-3">
        <p className="text-lg font-semibold text-brand-950">Victus AI</p>
        <p className="text-sm text-brand-700">{r.summaryTitle}</p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
                Pathway B · TOI result
              </p>
              <CardTitle className="mt-1 text-2xl">{quality.label}</CardTitle>
              <CardDescription>
                Method <span className="font-semibold text-brand-900">
                  {sq.method_selected.toUpperCase()}
                </span>{' '}
                · {sq.frames_used} frames analysed · pipeline{' '}
                <code className="font-mono text-xs">{assessment.pipeline_version}</code>
              </CardDescription>
            </div>
            <Badge tone={quality.tone}>{assessment.quality}</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {assessment.quality === ToiQuality.POOR ? (
            <Alert tone="danger">
              <AlertTitle>{r.recaptureRequired}</AlertTitle>
              <AlertDescription>
                Signal quality fell below the acceptable floor.{' '}
                {assessment.warnings.length > 0
                  ? `Reasons: ${assessment.warnings.join(', ')}.`
                  : null}{' '}
                Improve lighting, reduce motion, and ensure your face remains in frame.
              </AlertDescription>
            </Alert>
          ) : null}

          {Object.keys(assessment.biomarkers).length > 0 ? (
            <BiomarkerGrid biomarkers={assessment.biomarkers} />
          ) : null}

          <SignalQualityBlock assessment={assessment} />

          <MethodDetailsBlock assessment={assessment} />

          {assessment.warnings.length > 0 &&
          assessment.quality !== ToiQuality.POOR ? (
            <Alert tone="warning">
              <AlertTitle>{r.warnings}</AlertTitle>
              <AlertDescription>
                <ul className="list-disc space-y-1 pl-5">
                  {assessment.warnings.map((w) => (
                    <li key={w}>
                      <code className="font-mono text-xs">{w}</code>
                    </li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
        <CardFooter className="flex justify-between">
          <p className="text-xs text-brand-600">
            Assessment <code className="font-mono">{assessment.id.slice(0, 8)}…</code>{' '}
            recorded at{' '}
            {new Date(assessment.created_at).toLocaleString(fmtLoc, {
              dateStyle: 'medium',
              timeStyle: 'short',
            })}
          </p>
          <div className="print-hide flex gap-2">
            <Button onClick={() => window.print()} variant="outline" size="sm">
              {r.download}
            </Button>
            <Button onClick={onRestart} variant="outline" size="sm">
              {r.restart}
            </Button>
          </div>
        </CardFooter>
      </Card>
    </div>
  );
}

function BiomarkerGrid({
  biomarkers,
}: {
  biomarkers: Record<string, BiomarkerEstimate>;
}): React.ReactElement {
  const ordered: { key: string; v: BiomarkerEstimate }[] = [];
  for (const key of [
    'heart_rate',
    'respiratory_rate',
    'hrv_rmssd',
    'hrv_sdnn',
    'stress_index',
  ]) {
    const v = biomarkers[key];
    if (v) ordered.push({ key, v });
  }
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold text-brand-900">Biomarkers</h3>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {ordered.map(({ key, v }) => (
          <div
            key={key}
            className="rounded-[var(--radius-control)] border border-brand-100 bg-brand-50 p-3"
          >
            <dt className="text-xs font-semibold uppercase tracking-wider text-brand-700">
              {BIOMARKER_LABEL[key] ?? key}
            </dt>
            <dd className="mt-1 font-mono text-lg text-brand-950">
              {v.value.toFixed(1)}{' '}
              <span className="text-xs text-brand-600">{v.unit}</span>
            </dd>
            {v.ci_low !== null && v.ci_low !== undefined && v.ci_high !== null && v.ci_high !== undefined ? (
              <p className="mt-1 text-xs text-brand-600">
                95% CI {v.ci_low.toFixed(1)} – {v.ci_high.toFixed(1)} {v.unit}
              </p>
            ) : null}
            {v.experimental ? (
              <p className="mt-1 text-xs font-semibold text-[color:var(--color-state-yellow-fg)]">
                Experimental
              </p>
            ) : null}
          </div>
        ))}
      </dl>
    </div>
  );
}

function SignalQualityBlock({
  assessment,
}: {
  assessment: ToiAssessmentResponse;
}): React.ReactElement {
  const sq = assessment.signal_quality;
  const rows: { label: string; value: string }[] = [
    { label: 'SNR (CHROM)', value: `${sq.snr_chrom_db.toFixed(2)} dB` },
    { label: 'SNR (POS)', value: `${sq.snr_pos_db.toFixed(2)} dB` },
    {
      label: 'Motion stability',
      value: `${(sq.motion_score * 100).toFixed(0)}%`,
    },
    {
      label: 'Lighting stability',
      value: `${(sq.lighting_score * 100).toFixed(0)}%`,
    },
    {
      label: 'Face presence',
      value: `${(sq.face_presence_ratio * 100).toFixed(0)}%`,
    },
    { label: 'Duration', value: `${assessment.duration_s.toFixed(1)} s` },
  ];
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold text-brand-900">Signal quality</h3>
      <dl className="grid grid-cols-3 gap-3">
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

function MethodDetailsBlock({
  assessment,
}: {
  assessment: ToiAssessmentResponse;
}): React.ReactElement | null {
  const details = assessment.method_details;
  const chrom = details['chrom'] as
    | { snr_db?: number; peak_bpm?: number }
    | undefined;
  const pos = details['pos'] as
    | { snr_db?: number; peak_bpm?: number }
    | undefined;
  if (!chrom && !pos) return null;
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold text-brand-900">
        Method comparison
      </h3>
      <div className="grid grid-cols-2 gap-3">
        <MethodPanel name="CHROM" data={chrom} />
        <MethodPanel name="POS" data={pos} />
      </div>
      <p className="mt-2 text-xs text-brand-600">
        Server selected the method with the higher in-band SNR. Both methods
        are intentionally green-channel-agnostic for Fitzpatrick III–VI
        robustness.
      </p>
    </div>
  );
}

function MethodPanel({
  name,
  data,
}: {
  name: string;
  data: { snr_db?: number; peak_bpm?: number } | undefined;
}): React.ReactElement {
  return (
    <div className="rounded-[var(--radius-control)] border border-brand-100 p-3">
      <p className="text-xs font-semibold uppercase tracking-wider text-brand-700">
        {name}
      </p>
      <p className="mt-1 font-mono text-sm text-brand-950">
        {data?.peak_bpm !== undefined ? `${data.peak_bpm.toFixed(1)} bpm` : '—'}
      </p>
      <p className="text-xs text-brand-600">
        SNR{' '}
        <span className="font-mono">
          {data?.snr_db !== undefined ? `${data.snr_db.toFixed(2)} dB` : '—'}
        </span>
      </p>
    </div>
  );
}
