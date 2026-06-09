'use client';

import Link from 'next/link';
import { useCallback, useRef, useState, useTransition } from 'react';

import type {
  CalibrationRecordResponse,
  CalibrationStatsResponse,
  StudySessionResponse,
  ToiAssessmentResponse,
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
import type { HrRecorder } from '@/lib/ble/hr-recorder';
import type { HrRecorderSummary } from '@/lib/ble/types';
import { CaptureStep } from '../capture-step';
import type { CompletedCapture } from '../toi-client';
import { assessToiAction } from '@/server/toi-actions';
import {
  getCalibrationStatsAction,
  listCalibrationRecordsAction,
} from '@/server/calibration-actions';

import {
  ActiveSessionBanner,
  NoActiveSessionBanner,
} from './active-session-banner';
import { BleConnectPanel } from './ble-connect-panel';
import { BlandAltmanChart } from './bland-altman-chart';
import { ReferenceEntryForm, type BlePrefill } from './record-form';
import { RecentPairsTable } from './recent-pairs-table';
import { StatsPanel } from './stats-panel';

type Step = 'idle' | 'capturing' | 'analysing' | 'reference' | 'done';

export function CalibrationClient({
  initialStats,
  initialRecords,
  initialActiveSession,
}: {
  initialStats: CalibrationStatsResponse;
  initialRecords: CalibrationRecordResponse[];
  initialActiveSession: StudySessionResponse | null;
}): React.ReactElement {
  const [step, setStep] = useState<Step>('idle');
  const [assessment, setAssessment] = useState<ToiAssessmentResponse | null>(null);
  const [stats, setStats] = useState<CalibrationStatsResponse>(initialStats);
  const [records, setRecords] =
    useState<CalibrationRecordResponse[]>(initialRecords);
  const [error, setError] = useState<string | null>(null);
  const [blePrefill, setBlePrefill] = useState<BlePrefill | null>(null);
  const [bleDeviceLabel, setBleDeviceLabel] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const bleRecorderRef = useRef<HrRecorder | null>(null);

  const refreshStats = useCallback((): void => {
    startTransition(async () => {
      const [s, r] = await Promise.all([
        getCalibrationStatsAction(),
        listCalibrationRecordsAction(50),
      ]);
      setStats(s);
      setRecords(r);
    });
  }, []);

  const onBleRecorderChange = useCallback((rec: HrRecorder | null): void => {
    bleRecorderRef.current = rec;
  }, []);

  const onCaptureStart = useCallback((): void => {
    if (bleRecorderRef.current) {
      bleRecorderRef.current.start();
    }
  }, []);

  const captureBleSummary = useRef<HrRecorderSummary | null>(null);

  const onCaptureEnd = useCallback((): void => {
    if (bleRecorderRef.current?.isRecording()) {
      captureBleSummary.current = bleRecorderRef.current.stop();
    } else {
      captureBleSummary.current = null;
    }
  }, []);

  const onCaptureComplete = useCallback(
    (capture: CompletedCapture): void => {
      setError(null);
      setStep('analysing');
      const bleSummary = captureBleSummary.current;
      startTransition(async () => {
        const result = await assessToiAction({
          frames: capture.samples,
          sample_rate_hz: capture.sampleRateHz,
          duration_s: capture.durationS,
          motion_score: capture.motionScore,
          lighting_score: capture.lightingScore,
          face_presence_ratio: capture.facePresenceRatio,
        });
        if (!result.ok) {
          setError(result.error);
          setStep('idle');
          return;
        }
        setAssessment(result.assessment);
        if (result.assessment.quality === 'POOR') {
          setError(
            'Capture quality was POOR — re-record before pairing with a reference reading.',
          );
          setStep('idle');
          return;
        }
        // Build BLE prefill IF the recorder gathered enough samples.
        if (bleSummary && bleSummary.hr_sample_count >= 3) {
          setBlePrefill({
            hr_bpm: round1(bleSummary.median_hr_bpm),
            hr_sample_count: bleSummary.hr_sample_count,
            rr_intervals_ms: bleSummary.rr_intervals_ms,
            rmssd_ms: bleSummary.rmssd_ms,
            sdnn_ms: bleSummary.sdnn_ms,
            device_label: bleDeviceLabel,
          });
        } else {
          setBlePrefill(null);
        }
        setStep('reference');
      });
    },
    [bleDeviceLabel],
  );

  const onPairRecorded = useCallback(
    (record: CalibrationRecordResponse): void => {
      setRecords((prev) => [record, ...prev]);
      setStep('done');
      refreshStats();
      captureBleSummary.current = null;
      setBlePrefill(null);
    },
    [refreshStats],
  );

  const reset = useCallback((): void => {
    setAssessment(null);
    setStep('idle');
    setError(null);
    setBlePrefill(null);
    captureBleSummary.current = null;
  }, []);

  return (
    <div className="space-y-8">
      {initialActiveSession ? (
        <ActiveSessionBanner session={initialActiveSession} />
      ) : (
        <NoActiveSessionBanner />
      )}

      <BleConnectPanel
        onRecorderChange={onBleRecorderChange}
        onDeviceLabelChange={setBleDeviceLabel}
      />

      <Card>
        <CardHeader>
          <CardTitle>Record a new calibration pair</CardTitle>
          <CardDescription>
            If a BLE device is connected above, the reference HR + raw RR
            intervals stream automatically during the 30-s capture. Otherwise
            you can enter the reading manually after the capture completes.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {error ? (
            <Alert tone="danger">
              <AlertTitle>Capture failed</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {step === 'idle' ? (
            <div className="flex flex-wrap gap-3">
              <Button size="lg" onClick={() => setStep('capturing')}>
                Start a calibration capture
              </Button>
              <Button asChild variant="outline" size="lg">
                <Link href="/toi/calibration/study">Study management →</Link>
              </Button>
              <Button asChild variant="outline" size="lg">
                <Link href="/toi">Back to Pathway B</Link>
              </Button>
            </div>
          ) : null}

          {step === 'capturing' ? (
            <CaptureStep
              onCaptureComplete={onCaptureComplete}
              onCaptureStart={onCaptureStart}
              onCaptureEnd={onCaptureEnd}
              disabled={isPending}
            />
          ) : null}

          {step === 'analysing' ? (
            <Alert tone="info">
              <AlertTitle>Analysing capture…</AlertTitle>
              <AlertDescription>
                CHROM + POS pipelines running. Hold tight.
              </AlertDescription>
            </Alert>
          ) : null}

          {step === 'reference' && assessment ? (
            <ReferenceEntryForm
              assessment={assessment}
              prefill={blePrefill}
              onRecorded={onPairRecorded}
              onCancel={reset}
            />
          ) : null}

          {step === 'done' && assessment ? (
            <Alert tone="success">
              <AlertTitle>Pair recorded</AlertTitle>
              <AlertDescription>
                rPPG = {assessment.biomarkers['heart_rate']?.value.toFixed(1)} bpm
                paired and added to your statistics below.{' '}
                <button
                  onClick={reset}
                  className="font-semibold underline"
                  type="button"
                >
                  Record another
                </button>
                .
              </AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
      </Card>

      <StatsPanel stats={stats} pipelineVersion={stats.pipeline_version} />

      {stats.overall && stats.overall.n >= 2 ? (
        <Card>
          <CardHeader>
            <CardTitle>Bland-Altman agreement plot (HR)</CardTitle>
            <CardDescription>
              Each dot is a paired capture. Solid line is bias; dashed bands
              are 95% Limits of Agreement (bias ± 1.96 σ).
            </CardDescription>
          </CardHeader>
          <CardContent>
            <BlandAltmanChart stats={stats.overall} />
          </CardContent>
        </Card>
      ) : null}

      {stats.overall_hrv && stats.overall_hrv.n >= 2 ? (
        <Card>
          <CardHeader>
            <CardTitle>Bland-Altman agreement plot (HRV RMSSD)</CardTitle>
            <CardDescription>
              Only pairs where the reference device provided raw RR intervals
              (BLE chest straps; n = {stats.overall_hrv.n}).
            </CardDescription>
          </CardHeader>
          <CardContent>
            <BlandAltmanChart
              stats={{
                // Repurpose the HR Bland-Altman renderer with RMSSD axes.
                // The HR-specific summary stats are unused by the plot, so
                // they are zeroed rather than spread from the nullable
                // `stats.overall` (which would make every field optional).
                n: stats.overall_hrv.n,
                mae_bpm: 0,
                rmse_bpm: 0,
                bias_bpm: stats.overall_hrv.rmssd_bias_ms,
                std_diff_bpm: 0,
                loa_lower_bpm: stats.overall_hrv.rmssd_loa_lower_ms,
                loa_upper_bpm: stats.overall_hrv.rmssd_loa_upper_ms,
                pearson_r: null,
                pearson_p: null,
                ref_min: 0,
                ref_max: Math.max(...stats.overall_hrv.rmssd_means, 1),
                ref_mean: 0,
                means: stats.overall_hrv.rmssd_means,
                differences: stats.overall_hrv.rmssd_differences,
                flags: stats.overall_hrv.flags,
              }}
            />
            <p className="mt-2 text-xs text-brand-600">
              Axes: mean (rPPG + reference) / 2 in ms (X), rPPG − reference
              difference in ms (Y).
            </p>
          </CardContent>
        </Card>
      ) : null}

      {records.length > 0 ? (
        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-4">
            <div>
              <CardTitle>Recent calibration pairs</CardTitle>
              <CardDescription>
                Last {records.length} pairs, newest first. The BLE column
                marks auto-paired captures.
              </CardDescription>
            </div>
            <Button asChild variant="outline" size="sm">
              <a
                href={`${process.env.NEXT_PUBLIC_API_BASE_URL ?? ''}/calibration/export.csv`}
                target="_blank"
                rel="noreferrer"
              >
                Export CSV
              </a>
            </Button>
          </CardHeader>
          <CardContent>
            <RecentPairsTable records={records} />
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function round1(v: number): number {
  return Math.round(v * 10) / 10;
}
