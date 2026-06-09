/**
 * Shared types for the browser-side rPPG capture pipeline.
 *
 * The browser samples per-frame mean RGB over a face ROI, accumulates
 * timestamped samples in a ring buffer, and POSTs the buffer to FastAPI
 * (which owns the CHROM/POS chrominance pipeline). All client-side state is
 * confined to capture orchestration + live quality feedback.
 */

export interface RoiBox {
  /** Top-left corner in pixel coordinates of the video frame. */
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface RppgSample {
  /** Monotonic capture-start-relative milliseconds. */
  t_ms: number;
  r: number;
  g: number;
  b: number;
}

export interface FrameSampleResult {
  sample: RppgSample | null;
  /** Face landmark detection result for the current frame, if successful. */
  roi: RoiBox | null;
  /** Per-frame luminance (Rec. 709) used for lighting-stability tracking. */
  luminance: number | null;
}

export interface CaptureProgress {
  /** Total samples currently buffered (uniform-spaced not guaranteed). */
  sampleCount: number;
  /** Live quality estimators recomputed every K frames. */
  motionScore: number;
  lightingScore: number;
  facePresenceRatio: number;
  /** Mean of luminance over the trailing window — UI shows raw brightness. */
  meanLuminance: number;
  /** Capture-start-relative seconds elapsed. */
  elapsedSeconds: number;
}
