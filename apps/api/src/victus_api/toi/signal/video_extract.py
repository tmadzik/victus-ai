"""Server-side WhatsApp-video → rPPG RGB time-series extractor.

WHY THIS MODULE EXISTS
----------------------
In the browser capture path (``apps/web/src/lib/rppg/*``) the client samples
the forehead/malar ROI frame-by-frame with MediaPipe + a 2D canvas and POSTs a
*pre-extracted* RGB time-series to the API. The WhatsApp rail has no browser:
WhatsApp hands us a 30-second **video file** and nothing else. This module is
the server-side equivalent of ``RoiSampler`` + ``FaceLandmarker`` — it turns a
video into exactly the arrays ``run_rppg_pipeline`` already consumes.

It deliberately does **not** re-implement any signal processing. Its single job
is: ``video file -> (timestamps_seconds, rgb_samples, quality scalars)`` so that
the existing, tested CHROM/POS pipeline is fed identical inputs regardless of
whether the capture came from a phone browser or a WhatsApp upload.

DESIGN NOTES (for future devs)
------------------------------
* **ROI policy mirrors the clinical rationale in the business plan §3.3:** sample
  the forehead and both malar (cheek) regions — thin skin, high vascularity —
  and avoid the central nose/hyperpigmented and lower jaw/mouth zones. We derive
  these sub-regions geometrically from a face bounding box; landmark-based ROIs
  (MediaPipe FaceMesh) can be slotted in later via the ``face_detector`` hook
  without touching the rest of the pipeline.
* **cPanel-friendly:** the only heavy dependency is ``opencv-python-headless``
  (no GUI/X11). The Haar frontal-face cascade ships *inside* OpenCV
  (``cv2.data.haarcascades``) so there is no model file to download or vendor.
  Decoding runs in the background worker, never inside the WhatsApp webhook
  request (see Victus_Demonstrator_Build_Plan.md §4).
* **Testability:** face detection is injected via ``face_detector`` so the unit
  suite can feed a synthetic pulsating clip with a fixed ROI box and verify the
  full extractor → pipeline path recovers a known heart rate without needing a
  real face on camera.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# A face box in pixel coordinates: (x, y, w, h), top-left origin.
FaceBox = tuple[int, int, int, int]
# A detector maps a single BGR frame to a face box, or None if no face.
FaceDetector = Callable[[np.ndarray], FaceBox | None]

# Below this fraction of frames containing a detectable face, the capture is
# treated as unusable and the worker should ask the user to re-record.
MIN_FACE_PRESENCE_RATIO = 0.6
# Inter-frame-interval coefficient of variation above which we flag the clip as
# variable-FPS. Variable-FPS video silently corrupts rPPG timing; the plan (§6.1)
# lists constant frame rate as a non-negotiable capture-integrity rule. We do not
# reject here (the downstream pipeline resamples onto a uniform grid using the
# real per-frame timestamps we recover) — we surface a warning for the worker.
FPS_VARIABILITY_CV_WARN = 0.25


@dataclass(frozen=True)
class VideoExtraction:
    """The extractor's output — a drop-in for ``run_rppg_pipeline`` inputs.

    ``timestamps_seconds`` and ``rgb_samples`` align on axis 0 and feed straight
    into the pipeline. The remaining fields are the quality scalars the browser
    path computes client-side (``motion_score``, ``lighting_score``,
    ``face_presence_ratio``) plus diagnostics for the worker / audit log.
    """

    timestamps_seconds: np.ndarray  # shape (N,), seconds, monotonic
    rgb_samples: np.ndarray         # shape (N, 3), mean R,G,B over ROI, 0..255
    sample_rate_hz: float           # nominal container FPS
    duration_s: float
    motion_score: float             # 0..1, 1 = perfectly stable
    lighting_score: float           # 0..1, 1 = well-exposed and stable
    face_presence_ratio: float      # 0..1, fraction of frames with a face
    frames_total: int
    frames_with_face: int
    fps_is_constant: bool
    warnings: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        """True if enough face frames were found to attempt inference."""
        return (
            self.face_presence_ratio >= MIN_FACE_PRESENCE_RATIO
            and self.rgb_samples.shape[0] >= 1
        )

    def to_pipeline_kwargs(self) -> dict[str, object]:
        """Keyword args for ``run_rppg_pipeline`` (arrays + quality scalars)."""
        return {
            "timestamps_seconds": self.timestamps_seconds,
            "rgb_samples": self.rgb_samples,
            "nominal_sample_rate_hz": self.sample_rate_hz,
            "motion_score": self.motion_score,
            "lighting_score_client": self.lighting_score,
            "face_presence_ratio": self.face_presence_ratio,
        }

    def to_assessment_payload(self) -> dict[str, object]:
        """JSON body matching ``ToiAssessmentRequest`` (the /toi POST contract).

        Lets the WhatsApp worker reuse the existing TOI service/endpoint and its
        persistence + audit, rather than calling the pipeline directly.
        """
        frames = [
            {
                "t_ms": round(float(t) * 1000.0),
                "r": float(rgb[0]),
                "g": float(rgb[1]),
                "b": float(rgb[2]),
            }
            for t, rgb in zip(
                self.timestamps_seconds, self.rgb_samples, strict=True
            )
        ]
        return {
            "frames": frames,
            "sample_rate_hz": self.sample_rate_hz,
            "duration_s": self.duration_s,
            "motion_score": self.motion_score,
            "lighting_score": self.lighting_score,
            "face_presence_ratio": self.face_presence_ratio,
        }


def _haar_detector() -> FaceDetector:
    """Default detector: OpenCV's bundled Haar frontal-face cascade.

    Imported lazily so the base API wheel does not require OpenCV — only the
    worker that actually processes video installs the ``video`` extra.
    """
    import cv2

    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(str(cascade_path))
    if cascade.empty():  # pragma: no cover - defensive; cascade ships with cv2
        raise RuntimeError(f"Failed to load Haar cascade at {cascade_path}")

    def detect(frame_bgr: np.ndarray) -> FaceBox | None:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80)
        )
        if len(faces) == 0:
            return None
        # Largest detection wins — closest / most prominent face.
        x, y, w, h = max(faces, key=lambda f: int(f[2]) * int(f[3]))
        return int(x), int(y), int(w), int(h)

    return detect


def _roi_boxes(face: FaceBox) -> list[FaceBox]:
    """Forehead + left/right malar sub-boxes derived from a face box.

    Fractions are intentionally conservative to stay on well-vascularised skin
    and off the hairline, eyebrows, nostrils and mouth. They are geometric
    approximations of the landmark ROIs used client-side; tune against real
    Fitzpatrick III–VI clips during calibration.
    """
    x, y, w, h = face
    boxes: list[FaceBox] = []
    # Forehead: central 50% width, vertical band ~12%–28% down the face.
    boxes.append((x + int(0.25 * w), y + int(0.12 * h), int(0.50 * w), int(0.16 * h)))
    # Left malar (subject's left = image right): cheek band below the eye.
    boxes.append((x + int(0.60 * w), y + int(0.52 * h), int(0.22 * w), int(0.18 * h)))
    # Right malar.
    boxes.append((x + int(0.18 * w), y + int(0.52 * h), int(0.22 * w), int(0.18 * h)))
    return boxes


def _skin_mask(patch_bgr: np.ndarray) -> np.ndarray:
    """Boolean skin mask over a BGR patch using a YCrCb threshold.

    Suppresses hair, eyebrows, background and specular highlights that would
    otherwise contaminate the ROI mean. Threshold is the widely-used Cr∈[133,173],
    Cb∈[77,127] skin locus, which holds across Fitzpatrick bands (it keys on
    chrominance, not luminance, so it is not biased toward light skin).
    """
    import cv2

    ycrcb = cv2.cvtColor(patch_bgr, cv2.COLOR_BGR2YCrCb)
    cr = ycrcb[:, :, 1]
    cb = ycrcb[:, :, 2]
    return (cr >= 133) & (cr <= 173) & (cb >= 77) & (cb <= 127)


def _mean_rgb_over_rois(
    frame_bgr: np.ndarray, rois: list[FaceBox], *, skin_mask: bool
) -> tuple[float, float, float] | None:
    """Mean (R, G, B) over the union of ROI skin pixels for one frame."""
    h_img, w_img = frame_bgr.shape[:2]
    r_sum = g_sum = b_sum = 0.0
    n = 0
    for x, y, w, h in rois:
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(w_img, x + w), min(h_img, y + h)
        if x1 <= x0 or y1 <= y0:
            continue
        patch = frame_bgr[y0:y1, x0:x1]
        if patch.size == 0:
            continue
        if skin_mask:
            mask = _skin_mask(patch)
            if mask.sum() < 16:  # too few skin pixels — skip this ROI
                continue
            sel = patch[mask]
        else:
            sel = patch.reshape(-1, 3)
        # OpenCV is BGR; accumulate as RGB.
        b_sum += float(sel[:, 0].sum())
        g_sum += float(sel[:, 1].sum())
        r_sum += float(sel[:, 2].sum())
        n += sel.shape[0]
    if n == 0:
        return None
    return r_sum / n, g_sum / n, b_sum / n


def _motion_score(centroids: np.ndarray, face_w: float) -> float:
    """Map face-centroid jitter (normalised by face width) to 0..1.

    Stable head → score near 1. Large frame-to-frame displacement (which wrecks
    rPPG) → score toward 0. Threshold: a per-frame displacement of ~8% of the
    face width is treated as fully unstable.
    """
    if centroids.shape[0] < 2 or face_w <= 0:
        return 1.0
    disp = np.linalg.norm(np.diff(centroids, axis=0), axis=1)
    mean_disp_frac = float(disp.mean()) / face_w
    return float(np.clip(1.0 - mean_disp_frac / 0.08, 0.0, 1.0))


def _lighting_score(luminances: np.ndarray) -> float:
    """Score exposure level + temporal stability into 0..1.

    Penalises (a) being far from a mid-exposure target and (b) flicker. Both
    degrade the pulsatile signal; flicker especially aliases into the HR band.
    """
    if luminances.shape[0] == 0:
        return 0.0
    mean_lum = float(luminances.mean())
    # Triangular preference peaking at 128, zero at 0/255.
    level = 1.0 - abs(mean_lum - 128.0) / 128.0
    # Temporal stability: 1 - coefficient of variation, floored at 0.
    cv = float(luminances.std()) / (mean_lum + 1e-6)
    stability = max(0.0, 1.0 - cv * 4.0)
    return float(np.clip(0.5 * level + 0.5 * stability, 0.0, 1.0))


def extract_rgb_from_video(
    video_path: str | Path,
    *,
    max_seconds: float = 60.0,
    skin_mask: bool = True,
    face_detector: FaceDetector | None = None,
    redetect_every: int = 5,
) -> VideoExtraction:
    """Decode a video and produce the rPPG RGB time-series + quality scalars.

    Parameters
    ----------
    video_path:
        Path to the downloaded WhatsApp media file (mp4/3gp/etc).
    max_seconds:
        Hard cap on processed duration (matches ``MAX_CAPTURE_SECONDS``).
    skin_mask:
        Restrict ROI means to YCrCb skin pixels (recommended).
    face_detector:
        Injectable ``frame -> FaceBox|None``. Defaults to the Haar cascade.
        The unit suite injects a fixed-box detector for synthetic clips.
    redetect_every:
        Re-run face detection every N frames and hold the last box in between
        (detection is the expensive step; ROI sampling is cheap). Set to 1 to
        detect on every frame.

    Returns
    -------
    VideoExtraction
        ``.usable`` indicates whether enough face frames were captured.
    """
    import cv2

    detector = face_detector or _haar_detector()
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {video_path}")

    try:
        nominal_fps = float(cap.get(cv2.CAP_PROP_FPS)) or 30.0
        warnings: list[str] = []

        times_s: list[float] = []
        rgbs: list[tuple[float, float, float]] = []
        luminances: list[float] = []
        centroids: list[tuple[float, float]] = []
        face_widths: list[float] = []

        frames_total = 0
        frames_with_face = 0
        last_box: FaceBox | None = None
        frame_index = 0

        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                break

            pos_ms = float(cap.get(cv2.CAP_PROP_POS_MSEC))
            # Some containers report 0 for every frame; fall back to index/fps.
            t_s = pos_ms / 1000.0 if pos_ms > 0 else frame_index / nominal_fps
            if t_s > max_seconds:
                break

            frames_total += 1

            if last_box is None or frame_index % redetect_every == 0:
                detected = detector(frame_bgr)
                if detected is not None:
                    last_box = detected

            if last_box is not None:
                rois = _roi_boxes(last_box)
                mean_rgb = _mean_rgb_over_rois(
                    frame_bgr, rois, skin_mask=skin_mask
                )
                if mean_rgb is not None:
                    frames_with_face += 1
                    times_s.append(t_s)
                    rgbs.append(mean_rgb)
                    luminances.append(
                        0.2126 * mean_rgb[0]
                        + 0.7152 * mean_rgb[1]
                        + 0.0722 * mean_rgb[2]
                    )
                    bx, by, bw, bh = last_box
                    centroids.append((bx + bw / 2.0, by + bh / 2.0))
                    face_widths.append(float(bw))

            frame_index += 1

        ts = np.asarray(times_s, dtype=np.float64)
        rgb = np.asarray(rgbs, dtype=np.float64).reshape(-1, 3)
        lum = np.asarray(luminances, dtype=np.float64)
        cents = np.asarray(centroids, dtype=np.float64).reshape(-1, 2)

        duration_s = float(ts[-1] - ts[0]) if ts.shape[0] >= 2 else 0.0
        presence = frames_with_face / frames_total if frames_total else 0.0

        # Constant-frame-rate integrity check on the recovered timestamps.
        fps_is_constant = True
        if ts.shape[0] >= 3:
            intervals = np.diff(ts)
            mean_iv = float(intervals.mean())
            if mean_iv > 0:
                cv = float(intervals.std()) / mean_iv
                if cv > FPS_VARIABILITY_CV_WARN:
                    fps_is_constant = False
                    warnings.append("variable_frame_rate")

        if presence < MIN_FACE_PRESENCE_RATIO:
            warnings.append("insufficient_face_presence")

        mean_face_w = float(np.mean(face_widths)) if face_widths else 0.0
        motion = _motion_score(cents, mean_face_w)
        lighting = _lighting_score(lum)
        if motion < 0.5:
            warnings.append("excessive_motion")
        if lighting < 0.5:
            warnings.append("poor_lighting")

        return VideoExtraction(
            timestamps_seconds=ts,
            rgb_samples=rgb,
            sample_rate_hz=nominal_fps,
            duration_s=duration_s,
            motion_score=motion,
            lighting_score=lighting,
            face_presence_ratio=presence,
            frames_total=frames_total,
            frames_with_face=frames_with_face,
            fps_is_constant=fps_is_constant,
            warnings=warnings,
        )
    finally:
        cap.release()


def _main(argv: list[str] | None = None) -> int:  # pragma: no cover - dev CLI
    """Dev CLI: extract from a real clip and run it through the rPPG pipeline.

    Usage:  python -m victus_api.toi.signal.video_extract <video> [skin_mask=1]
    """
    import sys

    from victus_api.toi.signal.pipeline import run_rppg_pipeline

    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: python -m victus_api.toi.signal.video_extract <video>")
        return 2

    ex = extract_rgb_from_video(args[0])
    print(
        f"frames={ex.frames_total} face={ex.frames_with_face} "
        f"presence={ex.face_presence_ratio:.2f} dur={ex.duration_s:.1f}s "
        f"fps={ex.sample_rate_hz:.1f} motion={ex.motion_score:.2f} "
        f"lighting={ex.lighting_score:.2f} const_fps={ex.fps_is_constant} "
        f"warnings={ex.warnings}"
    )
    if not ex.usable:
        print("NOT USABLE — ask user to re-record.")
        return 1

    out = run_rppg_pipeline(**ex.to_pipeline_kwargs())  # type: ignore[arg-type]
    print(
        f"pipeline quality={out.quality} method={out.method_selected} "
        f"hr={out.heart_rate_bpm} bpm (ci={out.heart_rate_ci}) "
        f"rr={out.respiratory_rate_bpm} snr_sel="
        f"{max(out.snr_chrom_db, out.snr_pos_db):.1f}dB"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
