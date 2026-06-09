/**
 * Browser-side types for the Web Bluetooth Heart Rate Service integration.
 *
 * The Heart Rate Service is GATT UUID 0x180D. The Heart Rate Measurement
 * characteristic is 0x2A37 and ships notifications containing a flags byte
 * followed by either uint8 or uint16 HR and an optional list of RR intervals
 * in units of 1/1024 second.
 *
 * Spec: https://www.bluetooth.com/specifications/specs/heart-rate-service/
 */

export interface HrMeasurement {
  /** Capture-relative milliseconds (since recorder start). */
  t_ms: number;
  /** Heart-rate value in beats per minute. */
  hr_bpm: number;
  /** Optional RR intervals from this notification, in milliseconds. */
  rr_intervals_ms: number[];
  /** Sensor-contact bits (0–3) per spec, when present. ``null`` if absent. */
  contact: 'no_support' | 'not_detected' | 'detected' | null;
}

export interface HrRecorderSummary {
  /** Total number of HR notifications received during the window. */
  hr_sample_count: number;
  /** Mean HR over all notifications. */
  mean_hr_bpm: number;
  /** Median HR. */
  median_hr_bpm: number;
  /** Min / max HR observed. */
  min_hr_bpm: number;
  max_hr_bpm: number;
  /** Raw RR intervals concatenated from all notifications, in ms. */
  rr_intervals_ms: number[];
  /** RMSSD computed client-side from RR intervals; null if < 2 intervals. */
  rmssd_ms: number | null;
  /** SDNN computed client-side from RR intervals; null if < 2 intervals. */
  sdnn_ms: number | null;
  /** Capture-window duration in seconds. */
  duration_s: number;
}

export interface BleSupportInfo {
  apiAvailable: boolean;
  adapterAvailable: boolean | null;
  reason: string | null;
}
