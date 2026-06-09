'use client';

import { useEffect, useState, type FormEvent } from 'react';

import {
  type CalibrationRecordResponse,
  FitzpatrickScale,
  REFERENCE_DEVICE_LABELS,
  ReferenceDeviceType,
  type ToiAssessmentResponse,
} from '@victus/contracts';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { recordCalibrationAction } from '@/server/calibration-actions';

export interface BlePrefill {
  hr_bpm: number;
  hr_sample_count: number;
  rr_intervals_ms: number[];
  rmssd_ms: number | null;
  sdnn_ms: number | null;
  device_label: string | null;
}

export function ReferenceEntryForm({
  assessment,
  prefill,
  onRecorded,
  onCancel,
}: {
  assessment: ToiAssessmentResponse;
  prefill: BlePrefill | null;
  onRecorded: (record: CalibrationRecordResponse) => void;
  onCancel: () => void;
}): React.ReactElement {
  const rppgHr = assessment.biomarkers['heart_rate']?.value;
  const rppgRmssd = assessment.biomarkers['hrv_rmssd']?.value;
  const [device, setDevice] = useState<ReferenceDeviceType>(
    prefill ? ReferenceDeviceType.ECG_STRAP : ReferenceDeviceType.PULSE_OXIMETER,
  );
  const [label, setLabel] = useState(prefill?.device_label ?? '');
  const [hr, setHr] = useState(prefill ? String(prefill.hr_bpm) : '');
  const [rr, setRr] = useState('');
  const [fitz, setFitz] = useState<FitzpatrickScale | ''>('');
  const [notes, setNotes] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isPending, setIsPending] = useState(false);

  // If a prefill arrives after mount (e.g. capture finished after the form
  // mounted in a future flow), reflect it.
  useEffect(() => {
    if (prefill) {
      setHr(String(prefill.hr_bpm));
      if (prefill.device_label) setLabel(prefill.device_label);
      if (device === ReferenceDeviceType.PULSE_OXIMETER) {
        setDevice(ReferenceDeviceType.ECG_STRAP);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefill]);

  const submit = async (e: FormEvent<HTMLFormElement>): Promise<void> => {
    e.preventDefault();
    setError(null);
    const hrNum = Number(hr);
    if (!Number.isFinite(hrNum) || hrNum < 30 || hrNum > 240) {
      setError('Reference HR must be a number between 30 and 240 bpm.');
      return;
    }
    const rrNum = rr.trim() === '' ? null : Number(rr);
    if (rrNum !== null && (!Number.isFinite(rrNum) || rrNum < 4 || rrNum > 60)) {
      setError('Reference RR must be a number between 4 and 60 breaths/min, or blank.');
      return;
    }
    setIsPending(true);
    try {
      const result = await recordCalibrationAction({
        toi_assessment_id: assessment.id,
        reference_device_type: device,
        reference_device_label: label.trim() || null,
        reference_hr_bpm: hrNum,
        reference_rr_bpm: rrNum,
        auto_paired_from_ble: prefill !== null,
        reference_hr_sample_count: prefill?.hr_sample_count ?? null,
        reference_rr_intervals_ms:
          prefill && prefill.rr_intervals_ms.length > 0
            ? prefill.rr_intervals_ms
            : null,
        skin_tone_estimate: fitz === '' ? null : fitz,
        notes: notes.trim() || null,
      });
      if (!result.ok) {
        setError(result.error);
      } else {
        onRecorded(result.record);
      }
    } finally {
      setIsPending(false);
    }
  };

  return (
    <div className="space-y-4">
      <Alert tone="info">
        <AlertTitle>rPPG read this capture as</AlertTitle>
        <AlertDescription>
          <span className="font-mono text-base font-semibold text-brand-900">
            {rppgHr ? `${rppgHr.toFixed(1)} bpm` : '—'}
          </span>
          {rppgRmssd ? (
            <>
              {' '}· RMSSD <span className="font-mono">{rppgRmssd.toFixed(1)} ms</span>
            </>
          ) : null}
          {' '}· quality <span className="font-mono">{assessment.quality}</span>
          {' '}· method <span className="font-mono">
            {assessment.signal_quality.method_selected.toUpperCase()}
          </span>
        </AlertDescription>
      </Alert>

      {prefill ? (
        <Alert tone="success">
          <AlertTitle className="flex items-center gap-2">
            <Badge tone="green">BLE</Badge> Auto-paired from chest-strap stream
          </AlertTitle>
          <AlertDescription>
            <span className="font-mono text-base font-semibold text-brand-900">
              {prefill.hr_bpm.toFixed(1)} bpm
            </span>{' '}
            (median of {prefill.hr_sample_count} notifications) ·{' '}
            {prefill.rr_intervals_ms.length > 0 ? (
              <>
                <span className="font-mono">{prefill.rr_intervals_ms.length}</span>{' '}
                RR intervals received{' '}
                {prefill.rmssd_ms !== null ? (
                  <>
                    · client RMSSD ={' '}
                    <span className="font-mono">{prefill.rmssd_ms.toFixed(1)} ms</span>
                  </>
                ) : null}
              </>
            ) : (
              <>device did not provide RR intervals — HR only</>
            )}
            . You can still edit the HR below before submitting.
          </AlertDescription>
        </Alert>
      ) : null}

      {error ? (
        <Alert tone="danger">
          <AlertTitle>Cannot record pair</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2" noValidate>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="device">Reference device</Label>
          <select
            id="device"
            required
            value={device}
            onChange={(e) =>
              setDevice(e.target.value as ReferenceDeviceType)
            }
            className="flex h-10 w-full rounded-[var(--radius-control)] border border-brand-200 bg-white px-3 py-2 text-sm text-brand-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
          >
            {(Object.keys(REFERENCE_DEVICE_LABELS) as ReferenceDeviceType[]).map(
              (k) => (
                <option key={k} value={k}>
                  {REFERENCE_DEVICE_LABELS[k]}
                </option>
              ),
            )}
          </select>
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="label">Device label (optional)</Label>
          <Input
            id="label"
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            maxLength={120}
            placeholder="e.g. Wellue O2Ring, Apple Watch S9, Polar H10"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="hr">Reference HR (bpm)</Label>
          <Input
            id="hr"
            type="number"
            inputMode="numeric"
            required
            min={30}
            max={240}
            step="0.1"
            value={hr}
            onChange={(e) => setHr(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="rr">Reference RR (breaths/min, optional)</Label>
          <Input
            id="rr"
            type="number"
            inputMode="numeric"
            min={4}
            max={60}
            step="1"
            value={rr}
            onChange={(e) => setRr(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="fitz">Fitzpatrick skin tone (optional)</Label>
          <select
            id="fitz"
            value={fitz}
            onChange={(e) => setFitz(e.target.value as FitzpatrickScale | '')}
            className="flex h-10 w-full rounded-[var(--radius-control)] border border-brand-200 bg-white px-3 py-2 text-sm text-brand-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
          >
            <option value="">Not specified</option>
            {(['I', 'II', 'III', 'IV', 'V', 'VI'] as FitzpatrickScale[]).map(
              (f) => (
                <option key={f} value={f}>
                  Type {f}
                </option>
              ),
            )}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="notes">Notes (optional)</Label>
          <Input
            id="notes"
            type="text"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            maxLength={500}
            placeholder="Lighting, posture, anything that might matter."
          />
        </div>
        <div className="flex justify-between gap-3 sm:col-span-2">
          <Button type="button" variant="outline" onClick={onCancel} disabled={isPending}>
            Cancel
          </Button>
          <Button type="submit" disabled={isPending}>
            {isPending ? 'Recording…' : 'Record pair'}
          </Button>
        </div>
      </form>
    </div>
  );
}
