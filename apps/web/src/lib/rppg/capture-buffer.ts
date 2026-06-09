'use client';

import type { CaptureProgress, RoiBox, RppgSample } from './types';

/**
 * Bounded sample buffer + live quality estimators.
 *
 * The buffer holds at most ``maxFrames`` (= TOI_CAPTURE.MAX_FRAMES) samples;
 * older entries are dropped if the capture overshoots. The quality estimators
 * — motion stability, lighting stability, face-presence ratio — are computed
 * incrementally so the UI can render a live bar without recomputing from
 * scratch on every frame.
 *
 * The "motion score" is the inverse coefficient of variation of the ROI's
 * centre-point trajectory: ``1 − clip(CV_xy / CV_max, 0, 1)``. The
 * "lighting score" mirrors the server-side estimate (1 − CV_luminance).
 * Face-presence ratio is just ``frames_with_face / total_frames``.
 */
export class CaptureBuffer {
  private samples: RppgSample[] = [];

  private roiCentres: { x: number; y: number }[] = [];

  private luminances: number[] = [];

  private framesAttempted = 0;

  private framesWithFace = 0;

  private startTime: number | null = null;

  constructor(public readonly maxFrames: number) {}

  reset(): void {
    this.samples = [];
    this.roiCentres = [];
    this.luminances = [];
    this.framesAttempted = 0;
    this.framesWithFace = 0;
    this.startTime = null;
  }

  /** Returns ``true`` if this sample was retained. */
  push(args: {
    rgb: { r: number; g: number; b: number } | null;
    luminance: number | null;
    roi: RoiBox | null;
    timestampMs: number;
  }): boolean {
    this.framesAttempted += 1;
    if (this.startTime === null) this.startTime = args.timestampMs;
    if (args.rgb && args.roi && args.luminance !== null) {
      this.framesWithFace += 1;
      const t_ms = Math.max(0, Math.round(args.timestampMs - this.startTime));
      this.samples.push({ t_ms, r: args.rgb.r, g: args.rgb.g, b: args.rgb.b });
      this.roiCentres.push({
        x: args.roi.x + args.roi.width / 2,
        y: args.roi.y + args.roi.height / 2,
      });
      this.luminances.push(args.luminance);
      if (this.samples.length > this.maxFrames) {
        this.samples.shift();
        this.roiCentres.shift();
        this.luminances.shift();
      }
      return true;
    }
    return false;
  }

  get samplesView(): readonly RppgSample[] {
    return this.samples;
  }

  /** Median frame interval (ms) over the captured trajectory. */
  estimateSampleRateHz(): number {
    if (this.samples.length < 2) return 0;
    const intervals: number[] = [];
    for (let i = 1; i < this.samples.length; i += 1) {
      const a = this.samples[i - 1]?.t_ms ?? 0;
      const b = this.samples[i]?.t_ms ?? 0;
      const d = b - a;
      if (d > 0) intervals.push(d);
    }
    if (intervals.length === 0) return 0;
    intervals.sort((a, b) => a - b);
    const median = intervals[Math.floor(intervals.length / 2)] ?? 0;
    return median > 0 ? 1000 / median : 0;
  }

  progress(timestampMs: number): CaptureProgress {
    const start = this.startTime ?? timestampMs;
    return {
      sampleCount: this.samples.length,
      motionScore: this.computeMotionScore(),
      lightingScore: this.computeLightingScore(),
      facePresenceRatio:
        this.framesAttempted === 0
          ? 0
          : this.framesWithFace / this.framesAttempted,
      meanLuminance: this.meanLuminance(),
      elapsedSeconds: Math.max(0, (timestampMs - start) / 1000),
    };
  }

  private meanLuminance(): number {
    if (this.luminances.length === 0) return 0;
    let s = 0;
    for (const l of this.luminances) s += l;
    return s / this.luminances.length;
  }

  private computeMotionScore(): number {
    if (this.roiCentres.length < 4) return 1;
    let sumX = 0;
    let sumY = 0;
    for (const p of this.roiCentres) {
      sumX += p.x;
      sumY += p.y;
    }
    const n = this.roiCentres.length;
    const muX = sumX / n;
    const muY = sumY / n;
    let varX = 0;
    let varY = 0;
    for (const p of this.roiCentres) {
      varX += (p.x - muX) ** 2;
      varY += (p.y - muY) ** 2;
    }
    const stdX = Math.sqrt(varX / n);
    const stdY = Math.sqrt(varY / n);
    // ROI is ~80px wide for a typical capture; normalize against an empirical
    // 12px std (corresponds to small natural head sway) as the unit motion CV.
    const cv = (stdX + stdY) / 2 / 12;
    return Math.max(0, Math.min(1, 1 - cv));
  }

  private computeLightingScore(): number {
    if (this.luminances.length < 4) return 1;
    let s = 0;
    for (const l of this.luminances) s += l;
    const mu = s / this.luminances.length;
    if (mu <= 1) return 0;
    let v = 0;
    for (const l of this.luminances) v += (l - mu) ** 2;
    const std = Math.sqrt(v / this.luminances.length);
    const cv = std / mu;
    return Math.max(0, Math.min(1, 1 - cv));
  }
}
