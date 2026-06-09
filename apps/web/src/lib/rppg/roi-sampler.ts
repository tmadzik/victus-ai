'use client';

import type { RoiBox } from './types';

/**
 * Off-screen 2D canvas used to read ROI pixels out of the video stream.
 *
 * Sized to the ROI rather than the full frame — we only ever need to compute
 * a mean over the patch, so copying the entire frame is wasted work that
 * triggers GPU→CPU round-trips and JS heap pressure.
 */
export class RoiSampler {
  private canvas: HTMLCanvasElement | OffscreenCanvas;

  private ctx: CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;

  constructor() {
    if (typeof OffscreenCanvas !== 'undefined') {
      this.canvas = new OffscreenCanvas(1, 1);
      const c = this.canvas.getContext('2d', { willReadFrequently: true });
      if (!c) throw new Error('Failed to acquire OffscreenCanvas 2D context');
      this.ctx = c;
    } else {
      const el = document.createElement('canvas');
      el.width = 1;
      el.height = 1;
      this.canvas = el;
      const c = el.getContext('2d', { willReadFrequently: true });
      if (!c) throw new Error('Failed to acquire canvas 2D context');
      this.ctx = c;
    }
  }

  /**
   * Compute the mean (R, G, B) over the ROI patch and the per-frame luminance.
   *
   * Returns ``null`` if the ROI is degenerate (zero-sized) or the draw fails.
   */
  sample(
    video: HTMLVideoElement,
    roi: RoiBox,
  ): { r: number; g: number; b: number; luminance: number } | null {
    const w = Math.max(1, Math.floor(roi.width));
    const h = Math.max(1, Math.floor(roi.height));
    if (this.canvas.width !== w) this.canvas.width = w;
    if (this.canvas.height !== h) this.canvas.height = h;

    try {
      this.ctx.drawImage(
        video,
        Math.floor(roi.x),
        Math.floor(roi.y),
        w,
        h,
        0,
        0,
        w,
        h,
      );
    } catch {
      return null;
    }

    const data = this.ctx.getImageData(0, 0, w, h).data;
    let rSum = 0;
    let gSum = 0;
    let bSum = 0;
    const n = data.length / 4;
    if (n === 0) return null;
    for (let i = 0; i < data.length; i += 4) {
      rSum += data[i] ?? 0;
      gSum += data[i + 1] ?? 0;
      bSum += data[i + 2] ?? 0;
    }
    const r = rSum / n;
    const g = gSum / n;
    const b = bSum / n;
    const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    return { r, g, b, luminance };
  }
}
