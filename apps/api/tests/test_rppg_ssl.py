"""Self-supervised rPPG pretraining scaffold — runs on synthetic data."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

torch = pytest.importorskip("torch", reason="requires the 'ml' extra")

from victus_api.training.rppg_ssl import (  # noqa: E402
    RppgEncoder,
    RppgSSLConfig,
    load_encoder,
    nt_xent,
    pretrain,
    save_encoder_checkpoint,
    skin_tone_attenuation,
    synth_dataset,
)


def test_dark_skin_has_lower_snr() -> None:
    tones = ["I", "II", "III", "IV", "V", "VI"]
    vals = [skin_tone_attenuation(t) for t in tones]
    # Monotonically decreasing: darker skin → weaker pulsatile signal.
    assert vals == sorted(vals, reverse=True)
    assert vals[-1] < vals[0]


def test_synth_dataset_shape() -> None:
    windows, hrs = synth_dataset(16, length=128, seed=1)
    assert windows.shape == (16, 128)
    assert hrs.shape == (16,)
    assert float(hrs.min()) >= 50.0 and float(hrs.max()) <= 110.0


def test_encoder_shapes() -> None:
    enc = RppgEncoder(embed_dim=64, proj_dim=32)
    x = torch.randn(4, 200)
    assert enc.embed(x).shape == (4, 64)
    assert enc(x).shape == (4, 32)


def test_nt_xent_favours_aligned_views() -> None:
    torch.manual_seed(0)
    z = torch.randn(8, 16)
    aligned = nt_xent(z, z.clone())  # identical views — easy positives
    random = nt_xent(z, torch.randn(8, 16))  # unrelated — hard
    assert float(aligned) < float(random)


def test_pretraining_reduces_loss() -> None:
    windows, _ = synth_dataset(256, length=256, seed=3)
    cfg = RppgSSLConfig(steps=60, batch_size=32, seed=3)
    _encoder, history = pretrain(cfg, windows)
    assert len(history) == 60
    assert all(math.isfinite(v) for v in history)
    # The representation learns — recent loss is below the starting loss.
    assert min(history[-10:]) < history[0]


def test_checkpoint_roundtrip(tmp_path: Path) -> None:
    windows, _ = synth_dataset(64, length=128, seed=5)
    cfg = RppgSSLConfig(steps=5, batch_size=16, window_len=128, seed=5)
    encoder, history = pretrain(cfg, windows)
    path = tmp_path / "rppg_ssl.pt"
    save_encoder_checkpoint(encoder, cfg, path, history)

    reloaded, cfg2 = load_encoder(path)
    assert cfg2.window_len == 128
    x = torch.randn(2, 128)
    with torch.no_grad():
        assert torch.allclose(encoder.embed(x), reloaded.embed(x), atol=1e-5)
