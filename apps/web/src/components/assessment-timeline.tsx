import {
  DISEASE_LABELS,
  type Disease,
  type ToiAssessmentResponse,
  type ToiQuality,
  type TriageAssessmentResponse,
} from '@victus/contracts';

import { Badge, type BadgeProps, TriageStateBadge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';

// One unified, ordered stream across both pathways, newest first. Shared by the
// participant's own /history and the clinician's participant-record view.
type TimelineEntry =
  | { kind: 'triage'; at: number; data: TriageAssessmentResponse }
  | { kind: 'toi'; at: number; data: ToiAssessmentResponse };

const QUALITY_TONE: Record<ToiQuality, { tone: BadgeProps['tone']; label: string }> = {
  GOOD: { tone: 'green', label: 'Signal good' },
  DEGRADED: { tone: 'yellow', label: 'Signal degraded' },
  POOR: { tone: 'red', label: 'Signal too poor' },
};

const BIOMARKER_LABEL: Record<string, string> = {
  heart_rate: 'HR',
  respiratory_rate: 'RR',
  hrv_rmssd: 'HRV',
  hrv_sdnn: 'SDNN',
  stress_index: 'Stress',
};

export function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString('en-ZA', { dateStyle: 'medium', timeStyle: 'short' });
}

export function AssessmentTimeline({
  triage,
  toi,
  emptyHint,
}: {
  triage: TriageAssessmentResponse[];
  toi: ToiAssessmentResponse[];
  emptyHint?: React.ReactNode;
}): React.ReactElement {
  const entries: TimelineEntry[] = [
    ...triage.map((data) => ({
      kind: 'triage' as const,
      at: new Date(data.created_at).getTime(),
      data,
    })),
    ...toi.map((data) => ({
      kind: 'toi' as const,
      at: new Date(data.created_at).getTime(),
      data,
    })),
  ].sort((a, b) => b.at - a.at);

  if (entries.length === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-sm text-brand-600">
          {emptyHint ?? 'No assessments yet.'}
        </CardContent>
      </Card>
    );
  }

  return (
    <ol className="relative space-y-4 border-l border-brand-100 pl-6">
      {entries.map((entry) => (
        <li key={`${entry.kind}-${entry.data.id}`} className="relative">
          <span
            aria-hidden="true"
            className={`absolute -left-[1.6rem] top-2 h-3 w-3 rounded-full ring-4 ring-white ${
              entry.kind === 'triage' ? 'bg-brand-500' : 'bg-sky-500'
            }`}
          />
          {entry.kind === 'triage' ? (
            <TriageEntry data={entry.data} />
          ) : (
            <ToiEntry data={entry.data} />
          )}
        </li>
      ))}
    </ol>
  );
}

function TriageEntry({ data }: { data: TriageAssessmentResponse }): React.ReactElement {
  const trained = data.model_kind.startsWith('trained');
  return (
    <Card className="border-l-4 border-l-brand-500">
      <CardContent className="space-y-3 py-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Badge tone="brand">Pathway A — Triage</Badge>
            <TriageStateBadge state={data.overall_state} />
            {data.safety_override_triggered ? <Badge tone="red">Safety override</Badge> : null}
          </div>
          <time className="text-xs text-brand-600">{fmtDate(data.created_at)}</time>
        </div>

        <div className="flex flex-wrap gap-2">
          {data.per_disease.map((d) => (
            <span
              key={d.disease}
              className="inline-flex items-center gap-1 rounded-[var(--radius-control)] border border-brand-100 bg-brand-50 px-2 py-1 text-xs"
            >
              <span className="text-brand-700">{DISEASE_LABELS[d.disease as Disease]}</span>
              <TriageStateBadge state={d.state} />
            </span>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-brand-600">
          {data.derived_features.bmi != null ? (
            <span>
              BMI <span className="font-mono text-brand-900">{data.derived_features.bmi.toFixed(1)}</span>
            </span>
          ) : null}
          {data.derived_features.pulse_pressure_mmhg != null ? (
            <span>
              Pulse pressure{' '}
              <span className="font-mono text-brand-900">
                {data.derived_features.pulse_pressure_mmhg.toFixed(0)}
              </span>{' '}
              mmHg
            </span>
          ) : null}
          <span>
            Model{' '}
            <span className="font-mono text-brand-900">
              {trained ? 'DANN-EDL (trained)' : 'rule-based'}
            </span>
          </span>
        </div>

        {data.next_action && data.next_action !== '(historical)' ? (
          <p className="text-sm text-brand-800">{data.next_action}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}

function ToiEntry({ data }: { data: ToiAssessmentResponse }): React.ReactElement {
  const q = QUALITY_TONE[data.quality];
  const markers = Object.entries(data.biomarkers);
  return (
    <Card className="border-l-4 border-l-sky-500">
      <CardContent className="space-y-3 py-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Badge tone="brand">Pathway B — TOI</Badge>
            <Badge tone={q.tone}>{q.label}</Badge>
          </div>
          <time className="text-xs text-brand-600">{fmtDate(data.created_at)}</time>
        </div>

        {markers.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {markers.map(([key, est]) => (
              <span
                key={key}
                className="inline-flex items-baseline gap-1 rounded-[var(--radius-control)] border border-brand-100 bg-brand-50 px-2 py-1 text-xs"
              >
                <span className="text-brand-700">{BIOMARKER_LABEL[key] ?? key}</span>
                <span className="font-mono text-brand-900">{est.value.toFixed(0)}</span>
                <span className="text-brand-500">{est.unit}</span>
              </span>
            ))}
          </div>
        ) : (
          <p className="text-xs text-brand-600">
            No biomarkers extracted — signal did not clear the quality floor.
          </p>
        )}

        <div className="flex flex-wrap items-center gap-x-4 text-xs text-brand-600">
          <span>
            Duration <span className="font-mono text-brand-900">{data.duration_s.toFixed(0)}s</span>
          </span>
          <span>
            SNR{' '}
            <span className="font-mono text-brand-900">
              {data.signal_quality.method_selected === 'pos'
                ? data.signal_quality.snr_pos_db.toFixed(1)
                : data.signal_quality.snr_chrom_db.toFixed(1)}
            </span>{' '}
            dB
          </span>
          <span>
            Pipeline <span className="font-mono text-brand-900">{data.pipeline_version}</span>
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
