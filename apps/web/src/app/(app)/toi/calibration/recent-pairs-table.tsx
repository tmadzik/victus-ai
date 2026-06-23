'use client';

import {
  type CalibrationRecordResponse,
  REFERENCE_DEVICE_LABELS,
} from '@victus/contracts';

export function RecentPairsTable({
  records,
}: {
  records: CalibrationRecordResponse[];
}): React.ReactElement {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead className="border-b border-brand-200 text-left text-xs uppercase tracking-wider text-brand-700">
          <tr>
            <th className="py-2 pr-4">When</th>
            <th className="py-2 pr-4">BLE</th>
            <th className="py-2 pr-4">Reference</th>
            <th className="py-2 pr-4">Ref HR</th>
            <th className="py-2 pr-4">rPPG HR</th>
            <th className="py-2 pr-4">HR err</th>
            <th className="py-2 pr-4">Ref RMSSD</th>
            <th className="py-2 pr-4">rPPG RMSSD</th>
            <th className="py-2 pr-4">RMSSD err</th>
            <th className="py-2 pr-4">Quality</th>
            <th className="py-2 pr-4">Skin</th>
          </tr>
        </thead>
        <tbody>
          {records.map((r) => {
            const errColour =
              Math.abs(r.error_bpm) <= 3
                ? 'text-[color:var(--color-state-green-fg)]'
                : Math.abs(r.error_bpm) <= 8
                  ? 'text-[color:var(--color-state-yellow-fg)]'
                  : 'text-[color:var(--color-state-red-fg)]';
            const hrvErrColour =
              r.hrv_error_ms === null
                ? 'text-brand-400'
                : Math.abs(r.hrv_error_ms) <= 10
                  ? 'text-[color:var(--color-state-green-fg)]'
                  : Math.abs(r.hrv_error_ms) <= 25
                    ? 'text-[color:var(--color-state-yellow-fg)]'
                    : 'text-[color:var(--color-state-red-fg)]';
            return (
              <tr key={r.id} className="border-b border-brand-100">
                <td className="py-2 pr-4 font-mono text-xs text-brand-700">
                  {new Date(r.created_at).toLocaleString('en-GB', {
                    dateStyle: 'short',
                    timeStyle: 'short',
                  })}
                </td>
                <td className="py-2 pr-4">
                  {r.auto_paired_from_ble ? (
                    <span className="rounded-full border border-[color:var(--color-state-green-ring)]/40 bg-[color:var(--color-state-green-bg)] px-2 py-0.5 text-xs font-semibold uppercase text-[color:var(--color-state-green-fg)]">
                      BLE
                    </span>
                  ) : (
                    <span className="text-xs text-brand-500">manual</span>
                  )}
                </td>
                <td className="py-2 pr-4 text-brand-900">
                  {REFERENCE_DEVICE_LABELS[r.reference_device_type]}
                  {r.reference_device_label ? (
                    <span className="ml-1 text-brand-600">
                      ({r.reference_device_label})
                    </span>
                  ) : null}
                </td>
                <td className="py-2 pr-4 font-mono text-brand-700">
                  {r.reference_hr_bpm.toFixed(1)}
                </td>
                <td className="py-2 pr-4 font-mono text-brand-700">
                  {r.rppg_hr_bpm.toFixed(1)}
                </td>
                <td className={`py-2 pr-4 font-mono font-semibold ${errColour}`}>
                  {r.error_bpm >= 0 ? '+' : ''}
                  {r.error_bpm.toFixed(1)}
                </td>
                <td className="py-2 pr-4 font-mono text-brand-700">
                  {r.reference_hrv_rmssd_ms !== null
                    ? r.reference_hrv_rmssd_ms.toFixed(1)
                    : '—'}
                </td>
                <td className="py-2 pr-4 font-mono text-brand-700">
                  {r.rppg_hrv_rmssd_ms !== null
                    ? r.rppg_hrv_rmssd_ms.toFixed(1)
                    : '—'}
                </td>
                <td className={`py-2 pr-4 font-mono font-semibold ${hrvErrColour}`}>
                  {r.hrv_error_ms !== null
                    ? `${r.hrv_error_ms >= 0 ? '+' : ''}${r.hrv_error_ms.toFixed(1)}`
                    : '—'}
                </td>
                <td className="py-2 pr-4 font-mono text-xs text-brand-700">
                  {r.rppg_quality}
                </td>
                <td className="py-2 pr-4 font-mono text-xs text-brand-700">
                  {r.skin_tone_estimate ?? '—'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
