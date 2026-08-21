"""Step/sigma driven strength schedules for runtime H3 LoRA branches."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
import threading
from typing import Callable

import torch


def _explicit_values(text: str) -> tuple[float, ...]:
    tokens = [token for token in re.split(r"[,\s]+", str(text).strip()) if token]
    if not tokens:
        raise ValueError("explicit_strengths requires at least one value")
    try:
        values = tuple(float(token) for token in tokens)
    except ValueError as exc:
        raise ValueError("explicit_strengths contains a non-numeric value") from exc
    if not all(math.isfinite(value) for value in values):
        raise ValueError("explicit_strengths contains a NaN or infinite value")
    return values


def parse_rows(text: str) -> Callable[[int], bool]:
    """Parse one-based row selectors such as ``all``, ``1,3`` and ``2-4``."""
    value = str(text).strip().lower()
    if value == "all":
        return lambda _row: True
    if not value:
        raise ValueError("rows cannot be empty (use 'all' for every row)")
    selected: set[int] = set()
    for token in (part.strip() for part in value.split(",")):
        if not token:
            raise ValueError(f"invalid rows selector: {text!r}")
        match = re.fullmatch(r"(\d+)(?:\s*-\s*(\d+))?", token)
        if match is None:
            raise ValueError(f"invalid rows selector: {token!r}")
        first = int(match.group(1))
        last = int(match.group(2) or first)
        if first < 1 or last < first:
            raise ValueError(f"invalid rows range: {token!r}")
        selected.update(range(first, last + 1))
    return lambda row: row in selected


@dataclass(frozen=True)
class Schedule:
    rows: str = "all"
    start_strength: float = 1.0
    end_strength: float = 0.1
    curve: str = "linear"
    curve_power: float = 2.0
    explicit_strengths: str = ""
    start_percent: float = 0.0
    end_percent: float = 100.0
    domain: str = "steps"
    _matches: Callable[[int], bool] = field(init=False, repr=False, compare=False)
    _explicit: tuple[float, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        if self.curve not in {"linear", "cosine", "smoothstep", "power", "step", "explicit"}:
            raise ValueError(f"unknown strength curve: {self.curve}")
        if self.domain not in {"steps", "sigma"}:
            raise ValueError(f"unknown schedule domain: {self.domain}")
        numeric = (self.start_strength, self.end_strength, self.curve_power,
                   self.start_percent, self.end_percent)
        if not all(math.isfinite(float(value)) for value in numeric):
            raise ValueError("schedule values must be finite")
        if self.curve_power <= 0.0:
            raise ValueError("curve_power must be greater than zero")
        if not 0.0 <= self.start_percent <= self.end_percent <= 100.0:
            raise ValueError("start_percent/end_percent must satisfy 0 <= start <= end <= 100")
        object.__setattr__(self, "_matches", parse_rows(self.rows))
        values = _explicit_values(self.explicit_strengths) if self.curve == "explicit" else ()
        object.__setattr__(self, "_explicit", values)

    def matches(self, row_index: int) -> bool:
        return self._matches(row_index)

    def evaluate(self, progress: float) -> float:
        """Evaluate at normalized denoising progress (zero is the first call)."""
        progress = min(1.0, max(0.0, float(progress)))
        start = self.start_percent / 100.0
        end = self.end_percent / 100.0
        if progress < start:
            return float(self.start_strength)
        if progress > end:
            return float(self.end_strength)
        local = 1.0 if end == start else (progress - start) / (end - start)
        if self.curve == "explicit":
            index = min(len(self._explicit) - 1, round(local * (len(self._explicit) - 1)))
            return self._explicit[index]
        if self.curve == "linear":
            shaped = local
        elif self.curve == "cosine":
            shaped = 0.5 - 0.5 * math.cos(math.pi * local)
        elif self.curve == "smoothstep":
            shaped = local * local * (3.0 - 2.0 * local)
        elif self.curve == "power":
            shaped = local ** self.curve_power
        else:  # step: one abrupt transition at the middle of the interval
            shaped = 0.0 if local < 0.5 else 1.0
        return float(self.start_strength + shaped * (self.end_strength - self.start_strength))


def resolve(chain, row_index: int) -> Schedule | None:
    """Return the last schedule link selecting this one-based stack row."""
    if chain is None:
        return None
    links = (chain,) if isinstance(chain, Schedule) else chain
    result = None
    for item in links:
        if item.matches(row_index):
            result = item
    return result


def _scalar_sigma(sigma) -> torch.Tensor:
    value = torch.as_tensor(sigma).detach().float().flatten()
    if value.numel() == 0:
        return torch.tensor(0.0)
    return value.max()


def progress_from(sigma, transformer_options: dict, domain: str = "steps") -> float:
    """Resolve normalized denoising progress from ComfyUI's sampler metadata."""
    current = _scalar_sigma(sigma)
    sample_sigmas = transformer_options.get("sample_sigmas")
    if sample_sigmas is None:
        return 0.0
    samples = torch.as_tensor(sample_sigmas).detach().float().flatten()
    if samples.numel() == 0:
        return 0.0
    current = current.to(samples.device)
    max_sigma = float(samples.max().item())
    sigma_progress = 1.0 if max_sigma <= 0.0 else 1.0 - float(current.item()) / max_sigma
    sigma_progress = min(1.0, max(0.0, sigma_progress))
    if domain == "sigma":
        return sigma_progress
    matches = torch.nonzero(torch.isclose(samples, current, rtol=1e-4), as_tuple=False)
    if matches.numel():
        index = int(matches[0].item())
        return min(1.0, index / max(1, samples.numel() - 2))
    return sigma_progress


class ScheduleState:
    """Per-thread live scales used by every branch in one stack node."""

    def __init__(self):
        self._local = threading.local()

    def set(self, scales: dict[str, torch.Tensor], bias_scales: dict[str, torch.Tensor]):
        self._local.scales = scales
        self._local.bias_scales = bias_scales

    def clear(self):
        self._local.scales = {}
        self._local.bias_scales = {}

    def scales_for(self, name: str):
        return getattr(self._local, "scales", {}).get(name)

    def bias_scales_for(self, name: str):
        return getattr(self._local, "bias_scales", {}).get(name)
