'use client';

import type {
  CalibrationStatsBlock,
  CalibrationStatsResponse,
  HrvCalibrationStatsBlock,
} from '@victus/contracts';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';

export function StatsPanel({
  stats,
  pipelineVersion,
}: {
  stats: CalibrationStatsResponse;
  pipelineVersion: string;
}): React.ReactElement {
  const overall = stats.overall;
  const overallHrv = stats.overall_hrv;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Agreement statistics</CardTitle>
        <CardDescription>
          Bland-Altman framework on rPPG HR vs reference HR. Calibration module{' '}
          <code className="font-mono text-xs">{pipelineVersion}</code>.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {!overall || overall.n < 2 ? (
          <Alert tone="info">
            <AlertTitle>Not enough pairs yet</AlertTitle>
            <AlertDescription>
              Record at least 2 paired captures for the bias / LoA / MAE block,
              and 30+ for a reliable Pearson r. The 95% Limits of Agreement
              tighten as you add more samples.
            </AlertDescription>
          </Alert>
        ) : (
          <OverallBlock block={overall} />
        )}

        {overallHrv && overallHrv.n >= 2 ? (
          <HrvOverallBlock block={overallHrv} />
        ) : null}

        {overall && overall.n >= 2 ? (
          <StratifiedSection
            title="By signal quality"
            entries={Object.entries(stats.by_quality)}
          />
        ) : null}
        {overall && overall.n >= 2 ? (
          <StratifiedSection
            title="By Fitzpatrick skin tone"
            entries={Object.entries(stats.by_fitzpatrick)}
          />
        ) : null}
        {overall && overall.n >= 2 ? (
          <StratifiedSection
            title="By reference device"
            entries={Object.entries(stats.by_reference_device)}
          />
        ) : null}
        {overall && overall.n >= 2 && Object.keys(stats.by_posture).length > 0 ? (
          <StratifiedSection
            title="By posture (study sessions)"
            entries={Object.entries(stats.by_posture)}
          />
        ) : null}
        {overall && overall.n >= 2 && Object.keys(stats.by_time_of_day).length > 0 ? (
          <StratifiedSection
            title="By time of day (study sessions)"
            entries={Object.entries(stats.by_time_of_day)}
          />
        ) : null}
        {overall && overall.n >= 2 && Object.keys(stats.by_subject).length > 0 ? (
          <StratifiedSection
            title="By subject (study sessions)"
            entries={Object.entries(stats.by_subject)}
          />
        ) : null}
      </CardContent>
    </Card>
  );
}

function HrvOverallBlock({
  block,
}: {
  block: HrvCalibrationStatsBlock;
}): React.ReactElement {
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold text-brand-900">
        HRV agreement (N = {block.n}, BLE chest-strap pairs only)
      </h3>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Cell
          label="RMSSD MAE"
          value={`${block.rmssd_mae_ms.toFixed(2)} ms`}
          hint="mean |rppg − ref|"
        />
        <Cell
          label="RMSSD RMSE"
          value={`${block.rmssd_rmse_ms.toFixed(2)} ms`}
          hint="root-mean-square error"
        />
        <Cell
          label="RMSSD bias"
          value={`${block.rmssd_bias_ms >= 0 ? '+' : ''}${block.rmssd_bias_ms.toFixed(2)} ms`}
          hint="mean(rppg − ref)"
        />
        <Cell
          label="RMSSD 95% LoA"
          value={`${block.rmssd_loa_lower_ms.toFixed(1)} → ${block.rmssd_loa_upper_ms.toFixed(1)}`}
          hint="bias ± 1.96 σ"
        />
        <Cell
          label="RMSSD Pearson r"
          value={
            block.rmssd_pearson_r !== null
              ? `${block.rmssd_pearson_r.toFixed(3)}${
                  block.rmssd_pearson_p !== null
                    ? `  (p=${block.rmssd_pearson_p.toExponential(2)})`
                    : ''
                }`
              : '—'
          }
          hint="rppg ~ ref linearity"
        />
        <Cell
          label="SDNN MAE"
          value={block.sdnn_mae_ms !== null ? `${block.sdnn_mae_ms.toFixed(2)} ms` : '—'}
          hint="mean |rppg − ref|"
        />
        <Cell
          label="SDNN bias"
          value={
            block.sdnn_bias_ms !== null
              ? `${block.sdnn_bias_ms >= 0 ? '+' : ''}${block.sdnn_bias_ms.toFixed(2)} ms`
              : '—'
          }
          hint="mean(rppg − ref)"
        />
        <Cell
          label="σ of RMSSD diffs"
          value={`${block.rmssd_std_diff_ms.toFixed(2)} ms`}
          hint="dispersion"
        />
      </dl>
      {block.flags.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {block.flags.map((f) => (
            <span
              key={f}
              className="rounded-full border border-[color:var(--color-state-yellow-ring)]/60 bg-[color:var(--color-state-yellow-bg)] px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider text-[color:var(--color-state-yellow-fg)]"
            >
              {f.replaceAll('_', ' ')}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function OverallBlock({ block }: { block: CalibrationStatsBlock }): React.ReactElement {
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold text-brand-900">Overall (N = {block.n})</h3>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Cell label="MAE" value={`${block.mae_bpm.toFixed(2)} bpm`} hint="mean |rppg − ref|" />
        <Cell label="RMSE" value={`${block.rmse_bpm.toFixed(2)} bpm`} hint="√mean((rppg−ref)²)" />
        <Cell
          label="Bias"
          value={`${block.bias_bpm >= 0 ? '+' : ''}${block.bias_bpm.toFixed(2)} bpm`}
          hint="mean(rppg − ref)"
        />
        <Cell
          label="95% LoA"
          value={`${block.loa_lower_bpm.toFixed(1)} → ${block.loa_upper_bpm.toFixed(1)}`}
          hint="bias ± 1.96 σ"
        />
        <Cell
          label="Pearson r"
          value={
            block.pearson_r !== null
              ? `${block.pearson_r.toFixed(3)}${block.pearson_p !== null ? `  (p=${block.pearson_p.toExponential(2)})` : ''}`
              : '—'
          }
          hint="rppg ~ ref linearity"
        />
        <Cell
          label="Reference range"
          value={`${block.ref_min.toFixed(0)} – ${block.ref_max.toFixed(0)} bpm`}
          hint={`mean ${block.ref_mean.toFixed(1)} bpm`}
        />
        <Cell label="σ of differences" value={`${block.std_diff_bpm.toFixed(2)} bpm`} hint="dispersion" />
      </dl>
      {block.flags.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {block.flags.map((f) => (
            <span
              key={f}
              className="rounded-full border border-[color:var(--color-state-yellow-ring)]/60 bg-[color:var(--color-state-yellow-bg)] px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider text-[color:var(--color-state-yellow-fg)]"
            >
              {f.replaceAll('_', ' ')}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function StratifiedSection({
  title,
  entries,
}: {
  title: string;
  entries: [string, CalibrationStatsBlock | null][];
}): React.ReactElement | null {
  const nonEmpty = entries.filter(([, b]) => b && b.n >= 1);
  if (nonEmpty.length === 0) return null;
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold text-brand-900">{title}</h3>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="border-b border-brand-200 text-left text-xs uppercase tracking-wider text-brand-700">
            <tr>
              <th className="py-2 pr-4">Cell</th>
              <th className="py-2 pr-4">N</th>
              <th className="py-2 pr-4">MAE (bpm)</th>
              <th className="py-2 pr-4">Bias (bpm)</th>
              <th className="py-2 pr-4">95% LoA</th>
              <th className="py-2 pr-4">Pearson r</th>
            </tr>
          </thead>
          <tbody>
            {nonEmpty.map(([key, b]) => {
              if (!b) return null;
              return (
                <tr key={key} className="border-b border-brand-100">
                  <td className="py-2 pr-4 font-mono text-xs text-brand-900">{key}</td>
                  <td className="py-2 pr-4 font-mono text-brand-700">{b.n}</td>
                  <td className="py-2 pr-4 font-mono text-brand-700">
                    {b.mae_bpm.toFixed(2)}
                  </td>
                  <td className="py-2 pr-4 font-mono text-brand-700">
                    {b.bias_bpm >= 0 ? '+' : ''}
                    {b.bias_bpm.toFixed(2)}
                  </td>
                  <td className="py-2 pr-4 font-mono text-brand-700">
                    {b.n >= 2
                      ? `${b.loa_lower_bpm.toFixed(1)} → ${b.loa_upper_bpm.toFixed(1)}`
                      : '—'}
                  </td>
                  <td className="py-2 pr-4 font-mono text-brand-700">
                    {b.pearson_r !== null ? b.pearson_r.toFixed(3) : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Cell({
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
