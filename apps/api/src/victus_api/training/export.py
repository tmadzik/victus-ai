"""Checkpoint serialisation — writes the state-dict + a JSON meta sidecar.

The sidecar is the contract between training and inference: it pins the
feature ordering, the label mapping, the scaler params, and the model
topology. ``EvidentialTorchModel`` refuses to load any checkpoint whose
sidecar disagrees with the runtime feature schema.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch
from torch import nn

from victus_api.training.scaling import StandardScaler


def save_checkpoint(
    *,
    model: nn.Module,
    checkpoint_path: Path,
    feature_names: tuple[str, ...],
    label_mapping: tuple[str, ...],
    hidden_dims: tuple[int, ...],
    scaler: StandardScaler,
    version: str,
    training_metrics: dict[str, Any],
    source_distribution: dict[str, int],
    class_distribution: dict[str, int],
    architecture: str = "sequential_v1",
    domain_mapping: tuple[str, ...] | None = None,
    domain_hidden: int | None = None,
    domain_distribution: dict[str, int] | None = None,
    disease_mapping: tuple[str, ...] | None = None,
) -> None:
    """Write the state_dict + a JSON meta sidecar.

    ``architecture`` discriminates between the supported topologies:

    * ``sequential_v1`` / ``dann_v1`` — single risk head (legacy).
    * ``sequential_multihead_v1`` / ``dann_multihead_v1`` — one evidential head
      per disease; the sidecar pins ``disease_mapping`` (head order) so the
      runtime reconstructs the correct number of heads.

    The runtime ``EvidentialTorchModel`` dispatches on this field to rebuild the
    correct module before ``load_state_dict``.
    """
    dann_architectures = {"dann_v1", "dann_multihead_v1"}
    multihead_architectures = {"sequential_multihead_v1", "dann_multihead_v1"}

    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), checkpoint_path)

    meta: dict[str, Any] = {
        "architecture": architecture,
        "feature_names": list(feature_names),
        "label_mapping": list(label_mapping),
        "hidden_dims": list(hidden_dims),
        "scaler": scaler.to_dict(),
        "version": version,
        "exported_at": datetime.now(tz=UTC).isoformat(),
        "training_metrics": training_metrics,
        "source_distribution": source_distribution,
        "class_distribution": class_distribution,
    }
    if architecture in dann_architectures:
        if domain_mapping is None or domain_hidden is None:
            raise ValueError(
                f"{architecture} checkpoints require domain_mapping and domain_hidden",
            )
        meta["domain_mapping"] = list(domain_mapping)
        meta["domain_hidden"] = int(domain_hidden)
        if domain_distribution is not None:
            meta["domain_distribution"] = domain_distribution
    if architecture in multihead_architectures:
        if disease_mapping is None:
            raise ValueError(
                f"{architecture} checkpoints require disease_mapping",
            )
        meta["disease_mapping"] = list(disease_mapping)

    meta_path = checkpoint_path.with_suffix(checkpoint_path.suffix + ".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
