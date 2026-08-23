"""AdaLN basis conversion between dense and curve MiniMax H3 checkpoints.

H3 ships in two forms.  A *dense* checkpoint feeds ``silu(time_embedder(t))``,
a 2688-dim vector, into every ``adaln_proj.linear``.  A *curve* (pruned)
checkpoint drops the time embedder and instead stores a precomputed
``adaln_t_table`` of shape ``[grid, k]`` (k = 8 locally); the linears then take
a k-dim input.  ComfyUI's tables are mean-centered, i.e. the two spaces are
related by

    S(t) = c + V @ table(t)          V: [2688, k],  c: [2688]

A LoRA trained on one form has an ``adaln_proj.linear.lora_A`` of the wrong
width for the other, which is why ComfyUI logs

    shape '[96768, 8]' is invalid for input of size 260112384

and silently skips the layer.  Stripping those pairs is not an acceptable fix:
on the turbo distillation LoRAs the constant term alone is ~100% of the
magnitude of ``dW @ S(t)``, so dropping adaLN discards essentially the whole
adapter.  Instead we change basis, which preserves rank:

    dense -> curve   A' = A @ V,       plus bias delta  B @ (A @ c)
    curve -> dense   A' = A @ pinv(V), plus bias delta -B @ (A' @ c)

The reverse direction needs the pseudo-inverse rather than the transpose: the
least-squares ``V`` spans the right subspace but its columns are not
orthonormal, so ``V.T`` would not satisfy ``M @ V == I``.

The bias delta is emitted as ``.diff_b``; ``comfy.lora.load_lora`` turns that
into a ``("diff",)`` patch on the sibling ``.bias``.  Without it the port is
nearly worthless.

``V`` and ``c`` are recovered by least squares of ``[1 | table]`` against the
silu grid.  The fit must use the *target model's own* table: comfy's tables are
mean-centered while some third-party bakes are not, so tables from different
checkpoints are not interchangeable even though each is self-consistent with
its own weights.
"""

from __future__ import annotations

import logging
import os

import torch

LOG = logging.getLogger(__name__)

GRID_FILENAME = "h3_silu_temb_grid.safetensors"
_GRID_TENSOR = "silu_t_emb_grid"

_grid_cache: dict[str, torch.Tensor] = {}
_basis_cache: dict[tuple, tuple[torch.Tensor, torch.Tensor]] = {}


def find_silu_grid(extra_dirs=()) -> str:
    """Locate ``h3_silu_temb_grid.safetensors`` in the usual places."""
    candidates = list(extra_dirs)
    try:
        import folder_paths
        candidates.append(os.path.join(folder_paths.models_dir, "h3_adaln"))
        candidates.append(folder_paths.get_folder_paths("loras")[0])
        candidates.append(os.path.join(folder_paths.models_dir, "diffusion_models"))
        candidates.append(folder_paths.get_folder_paths("custom_nodes")[0]
                          if "custom_nodes" in getattr(folder_paths, "folder_names_and_paths", {})
                          else os.path.join(os.path.dirname(folder_paths.models_dir), "custom_nodes"))
    except Exception:
        pass
    for base in candidates:
        if not base or not os.path.isdir(base):
            continue
        direct = os.path.join(base, GRID_FILENAME)
        if os.path.isfile(direct):
            return direct
        # one level down covers custom_nodes/<pack>/h3_silu_temb_grid.safetensors
        try:
            for entry in os.listdir(base):
                nested = os.path.join(base, entry, GRID_FILENAME)
                if os.path.isfile(nested):
                    return nested
        except OSError:
            continue
    return ""


def load_silu_grid(path: str) -> torch.Tensor:
    """Load the ``[grid, 2688]`` silu(t_emb) grid, cached by path."""
    cached = _grid_cache.get(path)
    if cached is not None:
        return cached
    from safetensors.torch import load_file
    sd = load_file(path)
    if _GRID_TENSOR not in sd:
        raise ValueError(f"{path} does not contain '{_GRID_TENSOR}'")
    grid = sd[_GRID_TENSOR].to(torch.float32)
    _grid_cache[path] = grid
    return grid


def fit_basis(table: torch.Tensor, grid: torch.Tensor):
    """Least-squares fit of ``grid ~= 1 c^T + table V^T``.

    ``table`` is the target model's ``adaln_t_table`` ``[G, k]``; ``grid`` is
    ``[G, 2688]``.  Returns ``(V [2688, k], c [2688])``.
    """
    if table.shape[0] != grid.shape[0]:
        raise ValueError(
            f"adaLN table grid ({table.shape[0]}) and silu grid ({grid.shape[0]}) "
            "have different resolutions; they must come from the same bake"
        )
    key = (id(table), table.shape, float(table.float().sum()), id(grid))
    cached = _basis_cache.get(key)
    if cached is not None:
        return cached

    t = table.to(torch.float64)
    s = grid.to(torch.float64)
    design = torch.cat([torch.ones(t.shape[0], 1, dtype=torch.float64), t], dim=1)  # [G, 1+k]
    solution = torch.linalg.lstsq(design, s).solution                                # [1+k, 2688]
    c = solution[0].contiguous()                                                     # [2688]
    v = solution[1:].transpose(0, 1).contiguous()                                    # [2688, k]

    residual = float((design @ solution - s).norm() / s.norm().clamp(min=1e-12))
    # The last two curve directions are near-degenerate (sigma_7 ~ sigma_8), so
    # they differ between bakes and a grid from a different build only agrees to
    # ~2e-3.  That is still ~6x below the int8 quantization floor, and vastly
    # better than dropping adaLN entirely, so only a much larger residual is
    # worth complaining about.
    if residual > 2e-2:
        LOG.warning(
            "H3 PowerLoraStack: adaLN basis fit residual %.2e is high - the silu grid "
            "and the checkpoint's adaln_t_table probably come from different bakes",
            residual,
        )
    else:
        LOG.info("H3 PowerLoraStack: adaLN basis fit residual %.2e", residual)

    out = (v.to(torch.float32), c.to(torch.float32), residual)
    _basis_cache[key] = out
    return out


def fit_table_to_table(source_table: torch.Tensor, target_table: torch.Tensor):
    """Map a source curve basis onto a target curve basis.

    Used when a LoRA ships its own ``adaln_t_table``: the two bakes span nearly
    the same subspace but with different rotations and centering, so a LoRA
    trained against one is wrong on the other even though the shapes match.
    Fitting ``source ~= a + target M`` needs no silu grid at all.

    Returns ``(M [k_src, k_tgt], a [k_src], residual)``.
    """
    # MMC: to the CPU as well as to float64. A model's own `adaln_t_table` is on
    # the compute device, the LoRA's comes off disk on the CPU, and lstsq on two
    # tensors from different devices raises (upstream AUDIT_REPORT H5). This fit
    # is [grid, 8] either way, so there is nothing to gain by doing it on a GPU.
    src = source_table.detach().to(device="cpu", dtype=torch.float64)
    tgt = target_table.detach().to(device="cpu", dtype=torch.float64)
    if src.shape[0] != tgt.shape[0]:
        raise ValueError(
            f"adaLN tables have different grid resolutions ({src.shape[0]} vs {tgt.shape[0]})"
        )
    design = torch.cat([torch.ones(tgt.shape[0], 1, dtype=torch.float64), tgt], dim=1)
    solution = torch.linalg.lstsq(design, src).solution      # [1+k_tgt, k_src]
    residual = float((design @ solution - src).norm() / src.norm().clamp(min=1e-12))
    a = solution[0].contiguous()                             # [k_src]
    m = solution[1:].transpose(0, 1).contiguous()            # [k_src, k_tgt]
    return m.to(torch.float32), a.to(torch.float32), residual


class AdalnContext:
    """Everything needed to move adaLN LoRA pairs between the two bases."""

    def __init__(self, target_dim: int, table=None, grid_path: str = ""):
        self.target_dim = int(target_dim)
        self.table = table
        self.grid_path = grid_path
        self.residual = None
        # MMC: one basis per source table, not one per stack. On a dense target
        # the fit belongs to the table the *LoRA* shipped, so a memo held on the
        # context handed the second curve LoRA of a stack the first one's basis —
        # plausibly shaped, silently wrong (upstream AUDIT_REPORT H1). A failure
        # is cached the same way, per table, so one unfittable LoRA no longer
        # stops the next one from being ported.
        self._bases = {}
        self._warned_no_table = False

    @property
    def is_curve(self) -> bool:
        return self.table is not None

    def basis(self, curve_table=None):
        """``(V, c, residual)`` relating the dense space to a curve basis.

        The fit needs whichever side of the conversion is the *curve* side.  On
        a pruned target that is the checkpoint's own table; on a dense target
        converting a curve-trained LoRA it has to be the table the LoRA shipped,
        because nothing else records which bake it was trained against.
        """
        table = self.table if self.table is not None else curve_table
        if table is None:
            if not self._warned_no_table:
                LOG.warning(
                    "H3 PowerLoraStack: cannot rebase adaLN onto a dense checkpoint - "
                    "the LoRA does not carry the adaln_t_table of the curve bake it "
                    "was trained against"
                )
                self._warned_no_table = True
            return None
        # MMC: keyed by what is in the table rather than by which object holds
        # it — a state dict is loaded, read and dropped per LoRA, so identity
        # says nothing about content and two bakes must not share a fit.
        key = (tuple(table.shape), float(table.float().sum()),
               float(table.float().abs().sum()))
        if key in self._bases:
            return self._bases[key]
        basis = None
        try:
            if not self.grid_path:
                raise ValueError(
                    f"no {GRID_FILENAME} found; put it in models/h3_adaln/ to enable "
                    "adaLN porting"
                )
            grid = load_silu_grid(self.grid_path)
            basis = fit_basis(table.detach().to("cpu"), grid)
            self.residual = basis[2]
        except Exception as exc:
            LOG.warning("H3 PowerLoraStack: adaLN porting unavailable (%s)", exc)
        self._bases[key] = basis
        return basis


def port_adaln_pairs(sd: dict, ctx: AdalnContext, source_table=None):
    """Rebase every ``adaln_proj.linear`` LoRA pair onto the target's basis.

    ``source_table`` is the LoRA's own ``adaln_t_table`` if it shipped one.
    That is the better route when available: two curve bakes can have the same
    width but different rotations and centering, so a LoRA whose adaLN width
    already matches may still be wrong on this checkpoint, and only the table
    reveals it.  It also needs no silu grid.

    Mutates nothing; returns ``(new_sd, stats)``.
    """
    stats = {"ported": 0, "skipped": 0, "ok": 0, "rebased": 0, "residual": None}
    modules: dict[str, dict] = {}
    for key in sd:
        if ".adaln_proj.linear." not in key:
            continue
        body, _, suffix = key.rpartition(".adaln_proj.linear.")
        modules.setdefault(body + ".adaln_proj.linear", {})[suffix] = key

    if not modules:
        return sd, stats

    # curve -> curve via the LoRA's own table, when it carries one
    table_map = None
    if source_table is not None and ctx.table is not None:
        try:
            m, a_const, residual = fit_table_to_table(source_table, ctx.table)
            table_map = (m, a_const)
            stats["residual"] = residual
            LOG.info("H3 PowerLoraStack: adaLN table-to-table fit residual %.2e", residual)
        except Exception as exc:
            LOG.warning("H3 PowerLoraStack: adaLN table rebase unavailable (%s)", exc)

    out = dict(sd)
    basis = None
    for module, parts in modules.items():
        a_key = parts.get("lora_A.weight") or parts.get("lora_down.weight")
        b_key = parts.get("lora_B.weight") or parts.get("lora_up.weight")
        if a_key is None or b_key is None:
            continue
        a = sd[a_key]
        if a.ndim != 2:
            continue
        source_dim = a.shape[1]
        b = sd[b_key]
        a32 = a.to(torch.float32)

        if table_map is not None and source_dim == table_map[0].shape[0]:
            m, a_const = table_map
            a_new = a32 @ m                            # [r, k_tgt]
            const = a32 @ a_const                      # [r]
            sign = 1.0
            kind = "rebased"
        elif source_dim == ctx.target_dim:
            stats["ok"] += 1
            continue
        else:
            if basis is None:
                basis = ctx.basis(curve_table=source_table)
            if basis is None:
                for key in parts.values():
                    out.pop(key, None)
                stats["skipped"] += 1
                continue
            v, c, residual = basis                     # V: [2688, k], c: [2688]
            stats["residual"] = residual
            if source_dim == v.shape[0] and ctx.target_dim == v.shape[1]:
                a_new = a32 @ v                        # [r, k]
                const = a32 @ c                        # [r]
                sign = 1.0
            elif source_dim == v.shape[1] and ctx.target_dim == v.shape[0]:
                a_new = a32 @ torch.linalg.pinv(v)     # [r, 2688]
                const = a_new @ c                      # [r]
                sign = -1.0
            else:
                LOG.warning(
                    "H3 PowerLoraStack: adaLN pair %s has width %d, expected %d or %d - skipped",
                    module, source_dim, v.shape[0], v.shape[1],
                )
                for key in parts.values():
                    out.pop(key, None)
                stats["skipped"] += 1
                continue
            kind = "ported"

        # comfy scales the A/B pair by alpha/rank inside the adapter but applies
        # a diff_b patch verbatim, so the factor has to be folded in here
        alpha_key = parts.get("alpha")
        scale = 1.0
        if alpha_key is not None:
            try:
                alpha = sd[alpha_key]
                scale = float(alpha.item() if hasattr(alpha, "item") else alpha) / a_new.shape[0]
            except Exception:
                scale = 1.0
        bias_delta = sign * scale * (b.to(torch.float32) @ const)

        out.pop(a_key, None)
        out.pop(b_key, None)
        out[module + ".lora_A.weight"] = a_new.to(a.dtype)
        out[module + ".lora_B.weight"] = b
        if alpha_key is not None and alpha_key != module + ".alpha":
            out.pop(alpha_key, None)
            out[module + ".alpha"] = sd[alpha_key]
        out[module + ".diff_b"] = bias_delta.to(b.dtype)
        stats[kind] += 1

    return out, stats


def read_target(diffusion_model):
    """Inspect a loaded H3 DiT for its adaLN input width and curve table."""
    table = getattr(diffusion_model, "adaln_t_table", None)
    dim = None
    try:
        dim = diffusion_model.blocks[0].adaln_proj.linear.weight.shape[1]
    except Exception:
        if table is not None:
            dim = int(table.shape[1])
    return dim, table
