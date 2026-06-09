'use client';

import type { FaceLandmarker, FaceLandmarkerResult } from '@mediapipe/tasks-vision';

import type { RoiBox } from './types';

/**
 * MediaPipe FaceLandmarker wrapper.
 *
 * Singleton-cached because instantiating the WASM runtime + model takes a few
 * hundred ms. Loaded lazily so the camera permission can be requested before
 * the bundle is materialised. WASM assets resolve from the official CDN — no
 * Next.js asset pipeline plumbing required.
 */

let cached: Promise<FaceLandmarker> | null = null;

const WASM_BASE = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision/wasm';
const MODEL_URL =
  'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task';

export async function getFaceLandmarker(): Promise<FaceLandmarker> {
  if (cached) return cached;
  cached = (async () => {
    const { FaceLandmarker, FilesetResolver } = await import(
      '@mediapipe/tasks-vision'
    );
    const fileset = await FilesetResolver.forVisionTasks(WASM_BASE);
    return FaceLandmarker.createFromOptions(fileset, {
      baseOptions: {
        modelAssetPath: MODEL_URL,
        delegate: 'GPU',
      },
      runningMode: 'VIDEO',
      numFaces: 1,
      outputFaceBlendshapes: false,
      outputFacialTransformationMatrixes: false,
    });
  })();
  return cached;
}

/**
 * Forehead-centred ROI derived from MediaPipe FaceMesh landmarks.
 *
 * The forehead is preferred over the cheeks because (a) it is large, (b) it
 * suffers less from talking / expression motion, and (c) it carries strong
 * rPPG signal at all Fitzpatrick types. MediaPipe FaceMesh indices used:
 *
 * - 10  → forehead top centre
 * - 67  → forehead top-left
 * - 297 → forehead top-right
 * - 151 → forehead bottom centre (just above brows)
 * - 9   → glabella (between brows)
 *
 * The returned box is the axis-aligned bounding box of those landmarks
 * shrunken 20% horizontally and 30% vertically so the patch sits cleanly
 * inside the skin region away from hairline / brows.
 */
export function extractForeheadRoi(
  result: FaceLandmarkerResult,
  videoWidth: number,
  videoHeight: number,
): RoiBox | null {
  const faces = result.faceLandmarks;
  if (!faces || faces.length === 0) return null;
  const landmarks = faces[0];
  if (!landmarks || landmarks.length < 300) return null;

  const indices = [10, 67, 297, 151, 9];
  const points: { x: number; y: number }[] = [];
  for (const idx of indices) {
    const p = landmarks[idx];
    if (!p) continue;
    points.push({ x: p.x * videoWidth, y: p.y * videoHeight });
  }
  if (points.length < 3) return null;

  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const p of points) {
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.y > maxY) maxY = p.y;
  }
  const rawW = maxX - minX;
  const rawH = maxY - minY;
  if (rawW < 8 || rawH < 8) return null;

  const shrinkX = 0.2;
  const shrinkY = 0.3;
  const w = Math.max(8, rawW * (1 - shrinkX));
  const h = Math.max(8, rawH * (1 - shrinkY));
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  const x = Math.max(0, Math.min(videoWidth - w, cx - w / 2));
  const y = Math.max(0, Math.min(videoHeight - h, cy - h / 2));
  return { x, y, width: w, height: h };
}
