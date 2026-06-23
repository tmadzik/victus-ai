'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { TOI_CAPTURE } from '@victus/contracts';
import type { RppgFrame } from '@victus/contracts';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { useDictionary } from '@/i18n/context';
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
  const cap = useDictionary().toi.capture;
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number | null>(null);
  const bufferRef = useRef<CaptureBuffer | null>(null);
  const samplerRef = useRef<RoiSampler | null>(null);
  const startedAtRef = useRef<number | null>(null);
  // Monotonic token bumped on every (re)init and on stop(). An async camera
  // init that resolves AFTER teardown — e.g. React StrictMode's dev-only
  // double-mount, or a quick retry — can see it is stale and bail without
  // clobbering state or leaking a MediaStream.
  const initIdRef = useRef(0);

  const [state, setState] = useState<CaptureState>('idle');
  const [progress, setProgress] = useState<CaptureProgress | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [landmarkerReady, setLandmarkerReady] = useState(false);

  const stop = useCallback((): void => {
    initIdRef.current += 1; // invalidate any in-flight camera init
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
    const video = videoRef.current;
    if (!video) return;
    const myId = (initIdRef.current += 1);
    const isStale = (): boolean => myId !== initIdRef.current;
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
      // Torn down (unmount / retry) while awaiting permission — discard the
      // freshly-acquired stream and bail rather than attaching it to a dead
      // element.
      if (isStale()) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      streamRef.current = stream;
      video.srcObject = stream;
      // play() rejects with AbortError when a new load request (a srcObject
      // change or unmount) interrupts it — benign noise, not a capture
      // failure, so swallow it instead of surfacing "Capture error".
      try {
        await video.play();
      } catch (playErr) {
        if (playErr instanceof DOMException && playErr.name === 'AbortError') {
          return;
        }
        throw playErr;
      }
      if (isStale()) return;

      await getFaceLandmarker();
      if (isStale()) return;
      setLandmarkerReady(true);
      setState('idle');
    } catch (err) {
      // An interrupted load is not a user-facing error; everything else is.
      if (err instanceof DOMException && err.name === 'AbortError') return;
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

  // Demo-only (NEXT_PUBLIC_ENABLE_DEMO_CAPTURE=1): bypass the webcam and submit
  // a clean synthetic ROI-mean RGB trace — a green-dominant pulsatile AC on a
  // skin-tone DC plus a slow respiratory drift — so the CHROM/POS pipeline
  // recovers a high-SNR result and the full biomarker UI can be shown without a
  // perfect lighting/stillness setup. This is NOT a real measurement.
  const submitDemoSignal = useCallback((): void => {
    stop();
    const fps = 30;
    const seconds = TARGET_DURATION_S;
    const n = Math.round(fps * seconds);
    const hrHz = 66 / 60;
    const rrHz = 15 / 60;
    const samples: RppgFrame[] = [];
    for (let i = 0; i < n; i += 1) {
      const t = i / fps;
      const pulse = Math.sin(2 * Math.PI * hrHz * t);
      const resp = Math.sin(2 * Math.PI * rrHz * t);
      const jit = 0.03 * Math.sin(2 * Math.PI * 7.3 * t + 1.1);
      samples.push({
        t_ms: Math.round((i * 1000) / fps),
        r: 180 + 0.4 * pulse + 0.8 * resp + jit,
        g: 120 + 2.2 * pulse + 0.5 * resp + jit, // green channel strongest
        b: 110 + 0.9 * pulse + 0.4 * resp + jit,
      });
    }
    setErrorMessage(null);
    onCaptureStart?.();
    setState('done');
    onCaptureEnd?.();
    onCaptureComplete({
      samples,
      sampleRateHz: fps,
      durationS: seconds,
      motionScore: 1.0,
      lightingScore: 0.95,
      facePresenceRatio: 1.0,
    });
  }, [stop, onCaptureComplete, onCaptureStart, onCaptureEnd]);

  const demoEnabled = process.env.NEXT_PUBLIC_ENABLE_DEMO_CAPTURE === '1';

  const remaining = progress
    ? Math.max(0, TARGET_DURATION_S - progress.elapsedSeconds)
    : TARGET_DURATION_S;
  const pct = Math.min(100, (TARGET_DURATION_S - remaining) * (100 / TARGET_DURATION_S));

  return (
    <Card>
      <CardHeader>
        <CardTitle>{cap.title}</CardTitle>
        <CardDescription>
          Position your face squarely in the frame. A green box marks the
          forehead ROI; keep it stable for the full {TARGET_DURATION_S} seconds.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {errorMessage ? (
          <Alert tone="danger">
            <AlertTitle>{cap.error}</AlertTitle>
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
              <span className="font-semibold text-brand-900">{cap.capturing}</span>
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

        <div className="flex items-center justify-end gap-3">
          {state !== 'capturing' && demoEnabled ? (
            <Button
              onClick={submitDemoSignal}
              size="lg"
              variant="outline"
              disabled={disabled}
            >
              {cap.useDemoSignal}
            </Button>
          ) : null}
          {state !== 'capturing' ? (
            <Button
              onClick={startCapture}
              size="lg"
              disabled={!landmarkerReady || disabled || state === 'preparing'}
            >
              {state === 'preparing'
                ? cap.preparing
                : !landmarkerReady
                  ? cap.loadingLandmarker
                  : cap.start}
            </Button>
          ) : null}
        </div>
        {demoEnabled && state !== 'capturing' ? (
          <p className="text-right text-xs text-brand-600">
            Demo mode: submits a synthetic high-SNR pulse to exercise the
            pipeline — not a real measurement.
          </p>
        ) : null}
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
