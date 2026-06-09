'use client';

import { parseHeartRateMeasurement } from './heart-rate-service';
import type { HrMeasurement, HrRecorderSummary } from './types';

/**
 * Accumulates Heart Rate Measurement notifications across a capture window
 * and emits a summary (mean/median/min/max HR + RMSSD/SDNN derived from the
 * concatenated RR intervals). Designed to be `attach()`-ed to a connected
 * GATT characteristic and `start()/stop()`-ed by the capture orchestrator.
 *
 * Lifecycle::
 *
 *     const rec = new HrRecorder();
 *     rec.onUpdate(setLiveHr);            // optional live feedback
 *     rec.attach(connection.characteristic);
 *     rec.start();                        // resets buffers
 *     // ... rPPG capture runs in parallel ...
 *     const summary = rec.stop();         // returns aggregated metrics
 *     rec.detach();
 */
export class HrRecorder {
  private characteristic: BluetoothRemoteGATTCharacteristic | null = null;

  private samples: HrMeasurement[] = [];

  private rrIntervalsMs: number[] = [];

  private startMs: number | null = null;

  private listeners: ((sample: HrMeasurement) => void)[] = [];

  private boundHandler: ((event: Event) => void) | null = null;

  attach(characteristic: BluetoothRemoteGATTCharacteristic): void {
    if (this.characteristic === characteristic) return;
    this.detach();
    this.characteristic = characteristic;
    this.boundHandler = (event: Event): void => this.handleNotification(event);
    characteristic.addEventListener(
      'characteristicvaluechanged',
      this.boundHandler,
    );
  }

  detach(): void {
    if (this.characteristic && this.boundHandler) {
      this.characteristic.removeEventListener(
        'characteristicvaluechanged',
        this.boundHandler,
      );
    }
    this.characteristic = null;
    this.boundHandler = null;
  }

  onUpdate(listener: (sample: HrMeasurement) => void): () => void {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter((l) => l !== listener);
    };
  }

  start(): void {
    this.samples = [];
    this.rrIntervalsMs = [];
    this.startMs = performance.now();
  }

  stop(): HrRecorderSummary {
    const now = performance.now();
    const duration_s = this.startMs !== null ? (now - this.startMs) / 1000 : 0;
    const hrs = this.samples.map((s) => s.hr_bpm);
    const summary: HrRecorderSummary = {
      hr_sample_count: hrs.length,
      mean_hr_bpm: hrs.length > 0 ? mean(hrs) : 0,
      median_hr_bpm: hrs.length > 0 ? median(hrs) : 0,
      min_hr_bpm: hrs.length > 0 ? Math.min(...hrs) : 0,
      max_hr_bpm: hrs.length > 0 ? Math.max(...hrs) : 0,
      rr_intervals_ms: [...this.rrIntervalsMs],
      rmssd_ms: rmssd(this.rrIntervalsMs),
      sdnn_ms: sdnn(this.rrIntervalsMs),
      duration_s,
    };
    this.startMs = null;
    return summary;
  }

  isRecording(): boolean {
    return this.startMs !== null;
  }

  private handleNotification(event: Event): void {
    if (this.startMs === null) return;
    const target = event.target as BluetoothRemoteGATTCharacteristic;
    const value = target.value;
    if (!value) return;
    const sample = parseHeartRateMeasurement(value, this.startMs);
    if (!sample) return;
    this.samples.push(sample);
    if (sample.rr_intervals_ms.length > 0) {
      this.rrIntervalsMs.push(...sample.rr_intervals_ms);
    }
    for (const listener of this.listeners) listener(sample);
  }
}

function mean(arr: number[]): number {
  let s = 0;
  for (const v of arr) s += v;
  return s / arr.length;
}

function median(arr: number[]): number {
  if (arr.length === 0) return 0;
  const sorted = [...arr].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? ((sorted[mid - 1] ?? 0) + (sorted[mid] ?? 0)) / 2
    : sorted[mid] ?? 0;
}

function rmssd(rr: number[]): number | null {
  if (rr.length < 2) return null;
  let sumSq = 0;
  let count = 0;
  for (let i = 1; i < rr.length; i += 1) {
    const a = rr[i - 1] ?? 0;
    const b = rr[i] ?? 0;
    const d = b - a;
    sumSq += d * d;
    count += 1;
  }
  return count > 0 ? Math.sqrt(sumSq / count) : null;
}

function sdnn(rr: number[]): number | null {
  if (rr.length < 2) return null;
  const m = mean(rr);
  let v = 0;
  for (const x of rr) v += (x - m) ** 2;
  return Math.sqrt(v / (rr.length - 1));
}
