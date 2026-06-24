'use client';

import type { FaceLandmarker, FaceLandmarkerResult } from '@mediapipe/tasks-vision';
import { useCallback, useEffect, useRef, useState } from 'react';

import { TOI_CAPTURE } from '@victus/contracts';
import type { KioskCaptureRequest } from '@victus/contracts';

import { CaptureBuffer } from '@/lib/rppg/capture-buffer';
import { extractForeheadRoi, getFaceLandmarker } from '@/lib/rppg/face-landmarker';
import { RoiSampler } from '@/lib/rppg/roi-sampler';

const TARGET_DURATION_S = TOI_CAPTURE.TARGET_DURATION_S;
// Real-time validation gates (the spec): face must fill >40% of the frame and
// the scene must be neither too dark nor blown out.
const BBOX_MIN_RATIO = 0.4;
const ILLUMINATION_MIN = 0.5;
// Sustained good alignment (≈0.5 s at 30 fps) before auto-starting capture, so a
// single jittery frame doesn't trip it.
const ALIGN_HOLD_FRAMES = 15;

type Phase = 'preparing' | 'aligning' | 'capturing' | 'done' | 'error';

interface LiveMetrics {
  bboxRatio: number;
  illumination: number;
  faceVisible: boolean;
}

/** Fraction of the frame AREA covered by the face's landmark bounding box. */
function faceBboxRatio(result: FaceLandmarkerResult): number {
  const faces = result.faceLandmarks;
  if (!faces || faces.length === 0) return 0;
  const lm = faces[0];
  if (!lm || lm.length === 0) return 0;
  let minX = 1;
  let maxX = 0;
  let minY = 1;
  let maxY = 0;
  for (const p of lm) {
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.y > maxY) maxY = p.y;
  }
  return Math.max(0, Math.min(1, (maxX - minX) * (maxY - minY)));
}

/** Mean frame intensity in [0,1] from a downscaled hidden canvas. */
function frameIllumination(
  video: HTMLVideoElement,
  canvas: HTMLCanvasElement,
): number {
  const w = 48;
  const h = 36;
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  if (!ctx) return 0;
  ctx.drawImage(video, 0, 0, w, h);
  const { data } = ctx.getImageData(0, 0, w, h);
  let sum = 0;
  for (let i = 0; i < data.length; i += 4) {
    // Rec. 709 luma, normalised to [0,1].
    sum += (0.2126 * data[i]! + 0.7152 * data[i + 1]! + 0.0722 * data[i + 2]!) / 255;
  }
  return sum / (w * h);
}

/** Band quality: ~1 in the comfortable 0.30–0.80 range, tapering to 0. */
function illuminationQuality(mean: number): number {
  const lo = 0.18;
  const idealLo = 0.3;
  const idealHi = 0.8;
  const hi = 0.95;
  if (mean <= lo || mean >= hi) return 0;
  if (mean >= idealLo && mean <= idealHi) return 1;
  return mean < idealLo
    ? (mean - lo) / (idealLo - lo)
    : (hi - mean) / (hi - idealHi);
}

export function KioskCapture({
  onComplete,
}: {
  onComplete: (capture: KioskCaptureRequest) => void;
}): React.ReactElement {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const overlayRef = useRef<HTMLCanvasElement | null>(null);
  const hiddenRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number | null>(null);
  const bufferRef = useRef<CaptureBuffer | null>(null);
  const samplerRef = useRef<RoiSampler | null>(null);
  const landmarkerRef = useRef<FaceLandmarker | null>(null);
  const phaseRef = useRef<Phase>('preparing');
  const startedAtRef = useRef<number | null>(null);
  const alignFramesRef = useRef(0);
  // Running illumination / bbox accumulators over the capture window.
  const illSumRef = useRef(0);
  const bboxSumRef = useRef(0);
  const qualityFramesRef = useRef(0);
  const initIdRef = useRef(0);

  const [phase, setPhase] = useState<Phase>('preparing');
  const [metrics, setMetrics] = useState<LiveMetrics>({
    bboxRatio: 0,
    illumination: 0,
    faceVisible: false,
  });
  const [remaining, setRemaining] = useState<number>(TARGET_DURATION_S);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const setPhaseBoth = useCallback((p: Phase) => {
    phaseRef.current = p;
    setPhase(p);
  }, []);

  const stop = useCallback((): void => {
    initIdRef.current += 1;
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

  const finishCapture = useCallback(
    (now: number): void => {
      const buffer = bufferRef.current;
      stop();
      setPhaseBoth('done');
      if (!buffer) return;
      const progress = buffer.progress(now);
      const frames = [...buffer.samplesView];
      const sampleRate = buffer.estimateSampleRateHz();
      const sampleRateHz = sampleRate > 0 ? sampleRate : TOI_CAPTURE.TARGET_FPS;
      const durationS = Math.max(progress.elapsedSeconds, TOI_CAPTURE.MIN_DURATION_S);
      const qf = qualityFramesRef.current || 1;
      const illumination = illSumRef.current / qf;
      const bboxRatio = bboxSumRef.current / qf;

      const errorFlags: string[] = [];
      if (frames.length < TOI_CAPTURE.MIN_FRAMES) errorFlags.push('insufficient_frames');
      if (illuminationQuality(illumination) < ILLUMINATION_MIN) errorFlags.push('low_light');
      if (bboxRatio < BBOX_MIN_RATIO) errorFlags.push('face_too_small');

      // A composite acquisition-quality score the backend persists as-is.
      const signalQuality =
        (progress.motionScore + progress.lightingScore + progress.facePresenceRatio) / 3;

      onComplete({
        signal_quality_index: Math.max(0, Math.min(1, signalQuality)),
        illumination_score: Math.max(0, Math.min(1, illuminationQuality(illumination))),
        face_bbox_ratio: Math.max(0, Math.min(1, bboxRatio)),
        frame_count: frames.length,
        error_flags: errorFlags,
        rppg_signal: {
          frames,
          sample_rate_hz: sampleRateHz,
          duration_s: durationS,
        },
      });
    },
    [onComplete, setPhaseBoth, stop],
  );

  const tick = useCallback((): void => {
    const video = videoRef.current;
    const hidden = hiddenRef.current;
    const overlay = overlayRef.current;
    if (!video || !hidden) return;
    const now = performance.now();

    // The landmarker is resolved before the loop starts (initCamera awaits it),
    // so detectForVideo runs synchronously here.
    let detection: FaceLandmarkerResult | null = null;
    const lm = landmarkerRef.current;
    if (lm) {
      try {
        detection = lm.detectForVideo(video, now);
      } catch {
        detection = null;
      }
    }

    const roi = detection
      ? extractForeheadRoi(detection, video.videoWidth, video.videoHeight)
      : null;
    const bboxRatio = detection ? faceBboxRatio(detection) : 0;
    const illumination = frameIllumination(video, hidden);
    const illQuality = illuminationQuality(illumination);
    const faceVisible = roi !== null && bboxRatio > 0;

    // Overlay: green ROI box when sampling.
    if (overlay) {
      if (overlay.width !== video.videoWidth) overlay.width = video.videoWidth;
      if (overlay.height !== video.videoHeight) overlay.height = video.videoHeight;
      const octx = overlay.getContext('2d');
      if (octx) {
        octx.clearRect(0, 0, overlay.width, overlay.height);
        if (roi) {
          octx.strokeStyle = 'rgba(34,197,94,0.95)';
          octx.lineWidth = 3;
          octx.strokeRect(roi.x, roi.y, roi.width, roi.height);
        }
      }
    }

    setMetrics({ bboxRatio, illumination: illQuality, faceVisible });

    if (phaseRef.current === 'aligning') {
      const aligned = faceVisible && bboxRatio >= BBOX_MIN_RATIO && illQuality >= ILLUMINATION_MIN;
      alignFramesRef.current = aligned ? alignFramesRef.current + 1 : 0;
      if (alignFramesRef.current >= ALIGN_HOLD_FRAMES) {
        bufferRef.current = new CaptureBuffer(TOI_CAPTURE.MAX_FRAMES);
        if (!samplerRef.current) samplerRef.current = new RoiSampler();
        startedAtRef.current = now;
        illSumRef.current = 0;
        bboxSumRef.current = 0;
        qualityFramesRef.current = 0;
        setPhaseBoth('capturing');
      }
    } else if (phaseRef.current === 'capturing') {
      const elapsed = (now - (startedAtRef.current ?? now)) / 1000;
      setRemaining(Math.max(0, TARGET_DURATION_S - elapsed));
      const buffer = bufferRef.current;
      const sampler = samplerRef.current;
      const sample = roi && sampler ? sampler.sample(video, roi) : null;
      buffer?.push({
        rgb: sample ? { r: sample.r, g: sample.g, b: sample.b } : null,
        luminance: sample ? sample.luminance : null,
        roi,
        timestampMs: now,
      });
      illSumRef.current += illumination;
      bboxSumRef.current += bboxRatio;
      qualityFramesRef.current += 1;
      if (elapsed >= TARGET_DURATION_S) {
        finishCapture(now);
        return;
      }
    }

    rafRef.current = requestAnimationFrame(tick);
  }, [finishCapture, setPhaseBoth]);

  const initCamera = useCallback(async (): Promise<void> => {
    const video = videoRef.current;
    if (!video) return;
    const myId = (initIdRef.current += 1);
    const isStale = (): boolean => myId !== initIdRef.current;
    setErrorMessage(null);
    setPhaseBoth('preparing');
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
      if (isStale()) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      streamRef.current = stream;
      video.srcObject = stream;
      try {
        await video.play();
      } catch (playErr) {
        if (playErr instanceof DOMException && playErr.name === 'AbortError') return;
        throw playErr;
      }
      if (isStale()) return;
      landmarkerRef.current = await getFaceLandmarker();
      if (isStale()) return;
      setPhaseBoth('aligning');
      alignFramesRef.current = 0;
      rafRef.current = requestAnimationFrame(tick);
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      stop();
      setErrorMessage(
        err instanceof Error ? err.message : 'Unable to start the camera.',
      );
      setPhaseBoth('error');
    }
  }, [setPhaseBoth, stop, tick]);

  useEffect(() => {
    void initCamera();
    // Run once on mount; initCamera owns its own staleness guard.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pct = phase === 'capturing'
    ? Math.min(100, ((TARGET_DURATION_S - remaining) / TARGET_DURATION_S) * 100)
    : 0;

  return (
    <div className="w-full">
      <div className="relative mx-auto aspect-[4/3] w-full max-w-xl overflow-hidden rounded-3xl border border-brand-800 bg-black">
        <video
          ref={videoRef}
          playsInline
          muted
          className="h-full w-full -scale-x-100 object-cover"
          aria-label="Live camera preview"
        />
        <canvas
          ref={overlayRef}
          className="pointer-events-none absolute inset-0 h-full w-full -scale-x-100"
          aria-hidden="true"
        />
        <canvas ref={hiddenRef} className="hidden" aria-hidden="true" />

        {phase === 'capturing' ? (
          <div className="pointer-events-none absolute right-4 top-4 rounded-full bg-black/70 px-4 py-1.5 font-mono text-lg text-white">
            {remaining.toFixed(0)}s
          </div>
        ) : null}

        {phase === 'aligning' ? (
          <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-5 text-center">
            <p className="text-lg font-semibold text-white">{alignGuidance(metrics)}</p>
          </div>
        ) : null}
      </div>

      {phase === 'capturing' ? (
        <div className="mx-auto mt-5 w-full max-w-xl">
          <div className="h-3 w-full overflow-hidden rounded-full bg-brand-800">
            <div className="h-full bg-emerald-500 transition-all" style={{ width: `${pct}%` }} />
          </div>
          <p className="mt-3 text-center text-base text-brand-200">
            Hold still — measuring your vitals…
          </p>
        </div>
      ) : null}

      {phase === 'aligning' ? (
        <div className="mx-auto mt-5 grid w-full max-w-xl grid-cols-2 gap-3">
          <Gauge label="Face size" ok={metrics.bboxRatio >= BBOX_MIN_RATIO} value={metrics.bboxRatio} />
          <Gauge label="Lighting" ok={metrics.illumination >= ILLUMINATION_MIN} value={metrics.illumination} />
        </div>
      ) : null}

      {phase === 'preparing' ? (
        <p className="mt-6 text-center text-base text-brand-200">Starting camera…</p>
      ) : null}

      {phase === 'error' ? (
        <div className="mx-auto mt-5 w-full max-w-xl rounded-2xl border border-red-500/40 bg-red-500/10 p-4 text-center">
          <p className="font-semibold text-red-200">Camera unavailable</p>
          <p className="mt-1 text-sm text-red-200/80">{errorMessage}</p>
          <button
            onClick={() => void initCamera()}
            className="mt-3 rounded-full bg-white px-5 py-2 text-sm font-semibold text-brand-950"
          >
            Try again
          </button>
        </div>
      ) : null}
    </div>
  );
}

function alignGuidance(m: LiveMetrics): string {
  if (!m.faceVisible) return 'Look at the screen';
  if (m.illumination < ILLUMINATION_MIN) return 'Find brighter, even light';
  if (m.bboxRatio < BBOX_MIN_RATIO) return 'Move a little closer';
  return 'Hold still…';
}

function Gauge({
  label,
  ok,
  value,
}: {
  label: string;
  ok: boolean;
  value: number;
}): React.ReactElement {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="rounded-2xl border border-brand-800 p-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-brand-200">{label}</span>
        <span className={ok ? 'text-emerald-400' : 'text-amber-400'}>{ok ? '✓' : '…'}</span>
      </div>
      <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-brand-800">
        <div
          className={`h-full ${ok ? 'bg-emerald-500' : 'bg-amber-500'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
