"""Single-frame inference pipeline mirroring the Swift ``mlxdlss run`` first-frame path.

Order of operations: optional resample to the processing scale, vendor-aligned
network geometry, feature construction, the transformer, crop, head-to-RGB
composition, resample back, then the detail/colour split against the source.
"""
from __future__ import annotations

import json
import pathlib
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import torch

from . import model as reference
from .composition import compose_detail, compose_head, resample
from .features import PROFILES, AutomaticMask, NetworkGeometry, make_features

PRECISIONS = ("reference", "fast")
WEIGHT_FORMATS = tuple(f"dlssnr-logical-v{v}" for v in range(8, 19))
_SPEC_PATH = pathlib.Path(__file__).with_name("weight_spec.json")


def resolve_device(device: str | torch.device = "auto") -> torch.device:
    if isinstance(device, torch.device):
        return device
    if device == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    return torch.device(device)


def load_weight_spec() -> dict[str, dict[str, Any]]:
    return json.loads(_SPEC_PATH.read_text())["tensors"]


def validate_weights(weights: dict[str, torch.Tensor]) -> None:
    spec = load_weight_spec()
    missing = sorted(set(spec) - set(weights))
    if missing:
        raise ValueError(f"weights are missing {len(missing)} tensors, first: {missing[:3]}")
    for name, entry in spec.items():
        if list(weights[name].shape) != entry["shape"]:
            raise ValueError(f"{name}: expected shape {entry['shape']}, got {list(weights[name].shape)}")


def load_weights(path: str | pathlib.Path) -> dict[str, torch.Tensor]:
    """Load logical safetensors (``dlssnr-logical-v8`` … ``v18``, fully logical)."""
    from safetensors import safe_open

    with safe_open(str(path), framework="pt", device="cpu") as source:
        metadata = source.metadata() or {}
        if metadata.get("format") not in WEIGHT_FORMATS:
            raise ValueError(f"unsupported weight format {metadata.get('format')!r}; expected one of {WEIGHT_FORMATS[0]} … {WEIGHT_FORMATS[-1]}")
        if metadata.get("fully_logical") != "true":
            raise ValueError("weights must declare fully_logical=true")
        weights = {name: source.get_tensor(name) for name in source.keys()}
    validate_weights(weights)
    return weights


@dataclass
class EnhanceResult:
    image: np.ndarray
    network_extent: tuple[int, int]
    timings: dict[str, float] = field(default_factory=dict)


class NeuralRenderingPipeline:
    """Runs the recovered transformer on a single RGB frame.

    ``precision='reference'`` computes in float32 with the E4M3/half rounding
    points of the recovered graph (bit-faithful to the reference); ``'fast'``
    runs the same graph in float16 on GPU devices.
    """

    def __init__(self, weights: dict[str, torch.Tensor], *, device: str | torch.device = "auto", precision: str = "reference"):
        if precision not in PRECISIONS:
            raise ValueError(f"precision must be one of {PRECISIONS}")
        validate_weights(weights)
        self.device = resolve_device(device)
        self.precision = precision
        self.model = reference.NeuralRenderingModel(weights).eval()
        self.dtype = torch.float32
        if precision == "fast":
            if self.device.type == "cpu":
                import warnings

                warnings.warn("precision='fast' falls back to float32 on CPU", stacklevel=2)
            else:
                self.dtype = torch.float16
                self.model = self.model.to(torch.float16)
        self.model = self.model.to(self.device)

    @classmethod
    def from_safetensors(cls, path: str | pathlib.Path, *, device: str | torch.device = "auto", precision: str = "reference") -> "NeuralRenderingPipeline":
        return cls(load_weights(path), device=device, precision=precision)

    @torch.no_grad()
    def run_features(self, features: np.ndarray) -> np.ndarray:
        """Raw network: (height, width, 16) features -> (height, width, 4) head."""
        return self.run_features_batch(np.asarray(features, dtype=np.float32)[None])[0]

    @torch.no_grad()
    def run_features_batch(self, features: np.ndarray) -> np.ndarray:
        """Raw network on a batch: (count, height, width, 16) -> (count, height, width, 4)."""
        features = np.asarray(features, dtype=np.float32)
        if features.ndim != 4 or features.shape[3] != 16:
            raise ValueError("features must be (count, height, width, 16)")
        if features.shape[1] % 64 or features.shape[2] % 64:
            raise ValueError("feature extent must be a multiple of 64 (use NetworkGeometry.vendor_aligned)")
        tensor = torch.from_numpy(np.ascontiguousarray(features)).to(self.device, self.dtype)
        head = self.model(tensor)
        return head.to(torch.float32).cpu().numpy()

    def _controls(self, profile, normalized_style, local_tone_strength, local_structure_strength):
        if profile not in PROFILES:
            raise ValueError(f"profile must be one of {tuple(PROFILES)}")
        controls = dict(PROFILES[profile])
        if normalized_style is not None:
            controls["normalized_style"] = normalized_style
        if local_tone_strength is not None:
            controls["local_tone_strength"] = local_tone_strength
        if local_structure_strength is not None:
            controls["local_structure_strength"] = local_structure_strength
        return controls

    def prepare(
        self,
        image: np.ndarray,
        *,
        profile: str = "standard",
        processing_scale: float = 1.0,
        frame_index: int = 0,
        control_mask: np.ndarray | None = None,
        automatic_mask: AutomaticMask | None = None,
        normalized_style: float | None = None,
        local_tone_strength: float | None = None,
        local_structure_strength: float | None = None,
    ) -> "PreparedFrame":
        """Resample to the processing scale and build the network features (no network call)."""
        controls = self._controls(profile, normalized_style, local_tone_strength, local_structure_strength)
        if not 1 <= processing_scale <= 4:
            raise ValueError("processing_scale must be within [1, 4]")
        if control_mask is not None and processing_scale != 1:
            raise ValueError("a control mask requires processing_scale=1")
        source = np.asarray(image, dtype=np.float32)
        if source.ndim != 3 or source.shape[2] != 3:
            raise ValueError("image must be (height, width, 3)")
        started = time.perf_counter()
        processing = source
        if processing_scale != 1:
            processing = resample(
                source,
                int(round(source.shape[1] * processing_scale)),
                int(round(source.shape[0] * processing_scale)),
            )
        geometry = NetworkGeometry.vendor_aligned(processing.shape[1], processing.shape[0])
        features = make_features(
            processing, frame_index=frame_index, geometry=geometry, automatic_mask=automatic_mask, control_mask=control_mask, **controls
        )
        return PreparedFrame(source, processing, features, geometry, control_mask, time.perf_counter() - started)

    def finish(
        self,
        prepared: "PreparedFrame",
        head: np.ndarray,
        *,
        detail_strength: float = 1.0,
        colour_strength: float = 1.0,
        detail_radius: float = 4.0,
        intensity: float = 1.0,
        network_seconds: float = 0.0,
    ) -> EnhanceResult:
        """Compose the head over the frame, resample back and apply the detail/colour split."""
        started = time.perf_counter()
        composed = compose_head(
            prepared.geometry.crop(head), prepared.processing, control_mask=prepared.control_mask, intensity=intensity
        )
        if composed.shape[:2] != prepared.source.shape[:2]:
            composed = resample(composed, prepared.source.shape[1], prepared.source.shape[0])
        output = compose_detail(
            prepared.source, composed, detail_strength=detail_strength, colour_strength=colour_strength, radius=detail_radius
        )
        timings = {
            "preprocess": prepared.preprocess_seconds,
            "network": network_seconds,
            "postprocess": time.perf_counter() - started,
        }
        return EnhanceResult(output, (prepared.geometry.network_height, prepared.geometry.network_width), timings)

    def enhance(
        self,
        image: np.ndarray,
        *,
        profile: str = "standard",
        processing_scale: float = 1.0,
        detail_strength: float = 1.0,
        colour_strength: float = 1.0,
        detail_radius: float = 4.0,
        intensity: float = 1.0,
        frame_index: int = 0,
        control_mask: np.ndarray | None = None,
        automatic_mask: AutomaticMask | None = None,
        normalized_style: float | None = None,
        local_tone_strength: float | None = None,
        local_structure_strength: float | None = None,
    ) -> EnhanceResult:
        """Enhance one (height, width, 3) float32 RGB frame in [0, 1]."""
        prepared = self.prepare(
            image, profile=profile, processing_scale=processing_scale, frame_index=frame_index, control_mask=control_mask,
            automatic_mask=automatic_mask, normalized_style=normalized_style, local_tone_strength=local_tone_strength,
            local_structure_strength=local_structure_strength,
        )
        started = time.perf_counter()
        head = self.run_features(prepared.features)
        return self.finish(
            prepared, head, detail_strength=detail_strength, colour_strength=colour_strength, detail_radius=detail_radius,
            intensity=intensity, network_seconds=time.perf_counter() - started,
        )


@dataclass
class PreparedFrame:
    source: np.ndarray
    processing: np.ndarray
    features: np.ndarray
    geometry: NetworkGeometry
    control_mask: np.ndarray | None
    preprocess_seconds: float


class NeuralRenderingSession:
    """Frame-sequence wrapper: advances the noise frame index per frame.

    Temporal accumulation (motion vectors, depth, history) is the next phase;
    this class is the stable entry point for it, so callers can already feed
    frames through ``process`` and later gain temporal consistency without an
    API change.
    """

    def __init__(self, pipeline: NeuralRenderingPipeline, **enhance_options: Any):
        self.pipeline = pipeline
        self.options = enhance_options
        self.frame_index = 0

    def reset(self) -> None:
        self.frame_index = 0

    def process(self, image: np.ndarray) -> EnhanceResult:
        result = self.pipeline.enhance(image, frame_index=self.frame_index, **self.options)
        self.frame_index += 1
        return result
