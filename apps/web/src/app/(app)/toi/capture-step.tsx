'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { TOI_CAPTURE } from '@victus/contracts';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { CaptureBuffer } from '@/lib/rppg/capture-buffer';
import {
  extractForeheadRoi,
  getFaceLandmarker,
} from '@/lib/rppg/face-landmarker';
import { RoiSampler } from '@/lib/rppg/roi-sampler';
import type { CaptureProgress } from '@/lib/rppg/types';

import type { CompletedCapture } from './toi-client';

const TARGET_DURATION_S = TOI_CAPTURE.TARGET_DURATION_S;

type CaptureState = 'idle' | 'preparing' | 'capturing' | 'done';

export function CaptureStep({
  onCaptureComplete,
  onCaptureStart,
  onCaptureEnd,
  disabled,
}: {
  onCaptureComplete: (capture: CompletedCapture) => void;
  /** Fires the moment the 30-s window begins — used by the calibration
   *  client to start a parallel BLE HR recording. */
  onCaptureStart?: () => void;
  /** Fires when the 30-s window ends (just before `onCaptureComplete`). */
  onCaptureEnd?: () => void;
  disabled: boolean;
}): React.ReactElement {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number | null>(null);
  const bufferRef = useRef<CaptureBuffer | null>(null);
  const samplerRef = useRef<RoiSampler | null>(null);
  const startedAtRef = useRef<number | null>(null);

  const [state, setState] = useState<CaptureState>('idle');
  const [progress, setProgress] = useState<CaptureProgress | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [landmarkerReady, setLandmarkerReady] = useState(false);

  const stop = useCallback((): void => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) videoRef.current.srcObject = null;
  }, []);

  useEffect(() => () => stop(), [stop]);

  const initCamera = useCallback(async (): Promise<void> => {
    if (!videoRef.current) return;
    setErrorMessage(null);
    setState('preparing');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 640 },
          height: { ideal: 480 },
          frameRate: { ideal: 30, max: 60 },
          facingMode: 'user',
        },
        audio: false,
      });
      streamRef.current = stream;
      videoRef.current.srcObject = stream;
      await videoRef.current.play();

      await getFaceLandmarker();
      setLandmarkerReady(true);
      setState('idle');
    } catch (err) {
      stop();
      setErrorMessage(err instanceof Error ? err.message : String(err));
      setState('idle');
    }
  }, [stop]);

  useEffect(() => {
    void initCamera();
  }, [initCamera]);

  const startCapture = useCallback(async (): Promise<void> => {
    if (!videoRef.current || !canvasRef.current) return;
    if (!landmarkerReady) return;
    setErrorMessage(null);
    setState('capturing');

    const buffer = new CaptureBuffer(TOI_CAPTURE.MAX_FRAMES);
    bufferRef.current = buffer;
    if (!samplerRef.current) samplerRef.current = new RoiSampler();
    const sampler = samplerRef.current;
    const landmarker = await getFaceLandmarker();
    const overlayCtx = canvasRef.current.getContext('2d');
    if (!overlayCtx) {
      setErrorMessage('Unable to obtain 2D overlay context.');
      setState('idle');
      return;
    }

    const video = videoRef.current;
    startedAtRef.current = performance.now();
    onCaptureStart?.();

    const tick = (): void => {
      const now = performance.now();
      const elapsedSec = (now - (startedAtRef.current ?? now)) / 1000;
      if (
        elapsedSec >= TARGET_DURATION_S ||
        buffer.samplesView.length >= TOI_CAPTURE.MAX_FRAMES
      ) {
        const finalProgress = buffer.progress(now);
        setProgress(finalProgress);
        setState('done');
        onCaptureEnd?.();
        const sampleRateHz = buffer.estimateSampleRateHz();
        const samples = [...buffer.samplesView];
        if (samples.length < TOI_CAPTURE.MIN_FRAMES) {
          setErrorMessage(
            `Only ${samples.length} usable frames captured; need ≥ ${TOI_CAPTURE.MIN_FRAMES}. Improve lighting + face position and try again.`,
          );
          setState('idle');
          return;
        }
        onCaptureComplete({
          samples,
          sampleRateHz: sampleRateHz > 0 ? sampleRateHz : 30,
          durationS: Math.max(elapsedSec, TOI_CAPTURE.MIN_DURATION_S),
          motionScore: finalProgress.motionScore,
          lightingScore: finalProgress.lightingScore,
          facePresenceRatio: finalProgress.facePresenceRatio,
        });
        return;
      }

      let detection: ReturnType<typeof landmarker.detectForVideo> | null = null;
      try {
        detection = landmarker.detectForVideo(video, now);
      } catch {
        detection = null;
      }
      const roi = detection
        ? extractForeheadRoi(detection, video.videoWidth, video.videoHeight)
        : null;
      const sampleResult = roi ? sampler.sample(video, roi) : null;
      buffer.push({
        rgb: sampleResult
          ? { r: sampleResult.r, g: sampleResult.g, b: sampleResult.b }
          : null,
        luminance: sampleResult ? sampleResult.luminance : null,
        roi,
        timestampMs: now,
      });

      // Draw overlay.
      const cnv = canvasRef.current;
      if (cnv) {
        if (cnv.width !== video.videoWidth) cnv.width = video.videoWidth;
        if (cnv.height !== video.videoHeight) cnv.height = video.videoHeight;
        overlayCtx.clearRect(0, 0, cnv.width, cnv.height);
        if (roi) {
          overlayCtx.strokeStyle = 'rgba(34,197,94,0.95)';
          overlayCtx.lineWidth = 3;
          overlayCtx.strokeRect(roi.x, roi.y, roi.width, roi.height);
        }
      }

      setProgress(buffer.progress(now));
      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
  }, [landmarkerReady, onCaptureComplete, onCaptureStart, onCaptureEnd]);

  const remaining = progress
    ? Math.max(0, TARGET_DURATION_S - progress.elapsedSeconds)
    : TARGET_DURATION_S;
  const pct = Math.min(100, (TARGET_DURATION_S - remaining) * (100 / TARGET_DURATION_S));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Capture</CardTitle>
        <CardDescription>
          Position your face squarely in the frame. A green box marks the
          forehead ROI; keep it stable for the full {TARGET_DURATION_S} seconds.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {errorMessage ? (
          <Alert tone="danger">
            <AlertTitle>Capture error</AlertTitle>
            <AlertDescription>{errorMessage}</AlertDescription>
          </Alert>
        ) : null}

        <div className="relative mx-auto aspect-[4/3] w-full max-w-md overflow-hidden rounded-[var(--radius-card)] border border-brand-200 bg-black">
          <video
            ref={videoRef}
            playsInline
            muted
            className="h-full w-full -scale-x-100 object-cover"
            aria-label="Live camera preview"
          />
          <canvas
            ref={canvasRef}
            className="pointer-events-none absolute inset-0 h-full w-full -scale-x-100"
            aria-hidden="true"
          />
          {state === 'capturing' ? (
            <div className="pointer-events-none absolute right-3 top-3 rounded-full bg-black/60 px-3 py-1 text-xs font-mono text-white">
              {remaining.toFixed(1)}s
            </div>
          ) : null}
        </div>

        {state === 'capturing' && progress ? (
          <div>
            <div className="mb-2 flex justify-between text-xs">
              <span className="font-semibold text-brand-900">Capturing…</span>
              <span className="font-mono text-brand-700">
                {progress.sampleCount} frames
              </span>
            </div>
            <div
              className="h-2 w-full overflow-hidden rounded-full bg-brand-100"
              role="progressbar"
              aria-valuenow={pct}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                style={{ width: `${pct}%` }}
                className="h-full bg-brand-600 transition-all"
              />
            </div>
          </div>
        ) : null}

        {progress ? (
          <div className="grid grid-cols-3 gap-3">
            <QualityMeter label="Motion stability" value={progress.motionScore} />
            <QualityMeter label="Lighting stability" value={progress.lightingScore} />
            <QualityMeter label="Face presence" value={progress.facePresenceRatio} />
          </div>
        ) : null}

        <div className="flex justify-end gap-3">
          {state !== 'capturing' ? (
            <Button
              onClick={startCapture}
              size="lg"
              disabled={!landmarkerReady || disabled || state === 'preparing'}
            >
              {state === 'preparing'
                ? 'Preparing camera…'
                : !landmarkerReady
                  ? 'Loading face landmarker…'
                  : 'Start 30-second capture'}
            </Button>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function QualityMeter({
  label,
  value,
}: {
  label: string;
  value: number;
}): React.ReactElement {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  const tone =
    pct >= 70
      ? 'bg-[color:var(--color-state-green-ring)]'
      : pct >= 40
        ? 'bg-[color:var(--color-state-yellow-ring)]'
        : 'bg-[color:var(--color-state-red-ring)]';
  return (
    <div className="rounded-[var(--radius-control)] border border-brand-100 p-3">
      <p className="text-xs font-semibold uppercase tracking-wider text-brand-700">
        {label}
      </p>
      <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-brand-100">
        <div style={{ width: `${pct}%` }} className={`h-full ${tone}`} />
      </div>
      <p className="mt-1 text-right font-mono text-xs text-brand-700">
        {pct.toFixed(0)}%
      </p>
    </div>
  );
}
