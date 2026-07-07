"""Self-supervised rPPG representation pretraining — a scaffold for the
African-skin rPPG foundation model.

The single biggest scientific risk for an African deployment is that rPPG SNR
collapses on Fitzpatrick V–VI skin under uncontrolled light. Supervised labels
for HR/vitals are scarce and expensive; *representations* are not — self-
supervised contrastive learning needs no labels, which is exactly why it fits
here. This module stands up the whole pretraining pipeline so it is ready the
moment real, dark-skin capture volume exists.

What it is:
  * a synthetic rPPG generator whose pulsatile amplitude is graded by
    Fitzpatrick tone (darker → lower SNR) so the dark-skin challenge is modelled
    explicitly rather than ignored;
  * HR-preserving augmentations (phase roll, amplitude scale, jitter) and an
    NT-Xent (SimCLR) contrastive objective over a small 1-D CNN encoder;
  * checkpoint + model-card export.

What it is NOT: a validated model. It trains on SYNTHETIC signals only. The
dark-skin SNR model is a placeholder, and no output may be used clinically. Real
validation needs paired reference-device capture stratified by Fitzpatrick V–VI
and ambient light (see docs/PROSPECTIVE_VALIDATION_PLAN.md).

Run: ``python -m victus_api.training.rppg_ssl --synth 512 --steps 200 --out ...``
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch
from torch import nn

from victus_api.training.model_card import ModelCard

# Relative pulsatile amplitude (SNR proxy) by Fitzpatrick tone. Melanin absorbs
# the green light rPPG relies on, so the plethysmographic AC shrinks as skin
# darkens. These are illustrative, NOT measured values.
_FITZPATRICK_ATTENUATION: dict[str, float] = {
    "I": 1.00,
    "II": 0.90,
    "III": 0.78,
    "IV": 0.62,
    "V": 0.45,
    "VI": 0.32,
}


@dataclass
class RppgSSLConfig:
    window_len: int = 256
    fps: float = 30.0
    embed_dim: int = 64
    proj_dim: int = 32
    batch_size: int = 32
    steps: int = 100
    lr: float = 1e-3
    temperature: float = 0.5
    seed: int = 0


def skin_tone_attenuation(fitzpatrick: str) -> float:
    """Pulsatile-amplitude factor for a Fitzpatrick tone (I…VI). Darker → lower."""
    return _FITZPATRICK_ATTENUATION.get(fitzpatrick.upper(), 0.70)


def _synth_window(
    rng: np.random.Generator,
    *,
    length: int,
    fps: float,
    hr_bpm: float,
    attenuation: float,
    noise: float,
) -> np.ndarray:
    t = np.arange(length) / fps
    pulse = np.sin(2.0 * np.pi * (hr_bpm / 60.0) * t)
    resp = 0.3 * np.sin(2.0 * np.pi * 0.25 * t)  # slow respiratory baseline drift
    sig = attenuation * pulse + resp + rng.normal(0.0, noise, size=length)
    return sig.astype(np.float32)


def synth_dataset(
    n: int, *, length: int = 256, fps: float = 30.0, seed: int = 0
) -> tuple[np.ndarray, np.ndarray]:
    """``n`` synthetic rPPG windows spanning HR 50–110 bpm and Fitzpatrick I–VI
    attenuation with a range of noise (incl. the low-SNR dark-skin regime).
    Returns ``(windows[n, length], hr_bpm[n])`` — HR is for optional probing, not
    used by the self-supervised objective."""
    rng = np.random.default_rng(seed)
    tones = list(_FITZPATRICK_ATTENUATION)
    windows = np.empty((n, length), dtype=np.float32)
    hrs = np.empty(n, dtype=np.float32)
    for i in range(n):
        hr = float(rng.uniform(50.0, 110.0))
        tone = tones[int(rng.integers(len(tones)))]
        attenuation = skin_tone_attenuation(tone) * float(rng.uniform(0.8, 1.2))
        noise = float(rng.uniform(0.05, 0.40))
        windows[i] = _synth_window(
            rng, length=length, fps=fps, hr_bpm=hr, attenuation=attenuation, noise=noise
        )
        hrs[i] = hr
    return windows, hrs


def _augment(x: torch.Tensor) -> torch.Tensor:
    """HR-preserving augmentations for contrastive views. ``x``: ``[B, L]``.

    Phase roll (circular shift keeps the heart rate), amplitude scaling (SNR
    invariance) and Gaussian jitter (noise robustness) — the nuisances an rPPG
    representation should be invariant to while preserving pulsatility.
    """
    batch, length = x.shape
    scale = 0.7 + 0.6 * torch.rand(batch, 1)
    x = x * scale
    x = x + 0.05 * torch.randn_like(x)
    shifts = torch.randint(0, length, (batch,))
    return torch.stack([torch.roll(x[i], int(shifts[i].item())) for i in range(batch)])


class RppgEncoder(nn.Module):
    """Small 1-D CNN encoder + projection head for contrastive pretraining."""

    def __init__(self, embed_dim: int = 64, proj_dim: int = 32) -> None:
        super().__init__()
        self.backbone = nn.Sequential(
            nn.Conv1d(1, 32, kernel_size=7, padding=3),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.MaxPool1d(2),
            nn.Conv1d(32, embed_dim, kernel_size=5, padding=2),
            nn.BatchNorm1d(embed_dim),
            nn.ReLU(),
            nn.AdaptiveAvgPool1d(1),
        )
        self.proj = nn.Sequential(
            nn.Linear(embed_dim, embed_dim),
            nn.ReLU(),
            nn.Linear(embed_dim, proj_dim),
        )

    def embed(self, x: torch.Tensor) -> torch.Tensor:
        """``[B, L]`` → ``[B, embed_dim]`` representation (for downstream probes)."""
        return self.backbone(x.unsqueeze(1)).squeeze(-1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.proj(self.embed(x))


def nt_xent(z1: torch.Tensor, z2: torch.Tensor, temperature: float = 0.5) -> torch.Tensor:
    """NT-Xent (SimCLR) contrastive loss. ``z1``/``z2`` are the two views'
    projections, ``[B, d]``; positives are the matching rows."""
    batch = z1.shape[0]
    z = nn.functional.normalize(torch.cat([z1, z2], dim=0), dim=1)
    sim = (z @ z.t()) / temperature
    sim.masked_fill_(torch.eye(2 * batch, dtype=torch.bool), float("-inf"))
    targets = (torch.arange(2 * batch) + batch) % (2 * batch)
    return nn.functional.cross_entropy(sim, targets)


def pretrain(
    config: RppgSSLConfig, windows: np.ndarray
) -> tuple[RppgEncoder, list[float]]:
    """Contrastive pretraining loop. Returns the trained encoder and the
    per-step NT-Xent loss history."""
    torch.manual_seed(config.seed)
    encoder = RppgEncoder(config.embed_dim, config.proj_dim)
    optimizer = torch.optim.Adam(encoder.parameters(), lr=config.lr)
    data = torch.from_numpy(windows)
    n = data.shape[0]
    generator = torch.Generator().manual_seed(config.seed)

    history: list[float] = []
    encoder.train()
    for _ in range(config.steps):
        idx = torch.randint(0, n, (config.batch_size,), generator=generator)
        batch = data[idx]
        z1 = encoder(_augment(batch))
        z2 = encoder(_augment(batch))
        loss = nt_xent(z1, z2, config.temperature)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        history.append(float(loss.item()))
    encoder.eval()
    return encoder, history


def save_encoder_checkpoint(
    encoder: RppgEncoder,
    config: RppgSSLConfig,
    path: str | Path,
    history: list[float],
) -> None:
    torch.save(
        {
            "state_dict": encoder.state_dict(),
            "config": asdict(config),
            "final_loss": history[-1] if history else None,
        },
        path,
    )


def load_encoder(path: str | Path) -> tuple[RppgEncoder, RppgSSLConfig]:
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    config = RppgSSLConfig(**ckpt["config"])
    encoder = RppgEncoder(config.embed_dim, config.proj_dim)
    encoder.load_state_dict(ckpt["state_dict"])
    encoder.eval()
    return encoder, config


def rppg_ssl_model_card(
    version: str, *, steps: int, n_windows: int, final_loss: float
) -> ModelCard:
    return ModelCard(
        name="rPPG SSL encoder (pretraining scaffold)",
        version=version,
        intended_use=(
            "Self-supervised pretraining of an rPPG representation, to be fine-"
            "tuned and validated on real, Fitzpatrick-stratified reference-device "
            "capture. Research scaffold only."
        ),
        not_intended_use=(
            "Any clinical use, biomarker readout, or deployment. Trained on "
            "SYNTHETIC signals only; not validated on human data. Do not ship "
            "these weights."
        ),
        training_data=(
            f"{n_windows} synthetic rPPG windows spanning HR 50–110 bpm and "
            "Fitzpatrick I–VI attenuation (darker skin → lower pulsatile SNR), "
            "with added noise covering the low-SNR dark-skin / uncontrolled-light "
            "regime."
        ),
        evaluation_data=(
            "None (scaffold). Real validation requires paired reference-device "
            "capture stratified by Fitzpatrick V–VI and ambient light — see "
            "docs/PROSPECTIVE_VALIDATION_PLAN.md."
        ),
        metrics={
            "pretraining": {"final_nt_xent_loss": final_loss, "steps": float(steps)}
        },
        limitations=[
            "Synthetic-only; the dark-skin SNR grading is illustrative, not measured.",
            "Augmentations model phase/amplitude/noise nuisances only — real motion, "
            "video compression and illumination flicker are not simulated.",
        ],
        ethical_considerations=[
            "The entire purpose is equitable performance on Fitzpatrick V–VI; that "
            "can only be demonstrated on real dark-skin capture, never on this "
            "synthetic scaffold.",
        ],
        caveats=[
            "Use only to stand up the pretraining pipeline ahead of data.",
        ],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="victus-rppg-ssl",
        description="Self-supervised rPPG pretraining scaffold (synthetic).",
    )
    parser.add_argument("--synth", type=int, default=512, help="synthetic windows")
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=None, help="checkpoint path")
    args = parser.parse_args(argv)

    config = RppgSSLConfig(
        steps=args.steps, batch_size=args.batch_size, lr=args.lr, seed=args.seed
    )
    windows, _ = synth_dataset(args.synth, length=config.window_len, seed=args.seed)
    encoder, history = pretrain(config, windows)
    print(
        f"pretrained: steps={len(history)} "
        f"initial_loss={history[0]:.4f} final_loss={history[-1]:.4f}"
    )
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        save_encoder_checkpoint(encoder, config, args.out, history)
        card = rppg_ssl_model_card(
            "v0-scaffold", steps=len(history), n_windows=args.synth,
            final_loss=history[-1],
        )
        Path(args.out).with_suffix(".model_card.md").write_text(card.render_markdown())
        print(f"saved {args.out} (+ model card)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
