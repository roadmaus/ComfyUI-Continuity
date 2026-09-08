#!/usr/bin/env python3
"""Decode proven DLSSNR packed tensor families into ordinary ML tensors.

This is a research converter for a user-supplied packed safetensors file. It
implements only layouts that can be established from the embedded SM89 kernels
and NVIDIA's documented mma.m16n8k32 fragment mapping. Unknown tensor families
remain unsupported instead of being guessed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import re
import tempfile

import numpy
from safetensors.numpy import safe_open, save_file


PACKED_FORMAT = "dlssnr-WEIGHTS_HT-packed-u8-v2"
LOGICAL_FORMAT = "dlssnr-logical-v18"

_TENSOR_NAME = re.compile(r"^block(?P<block>\d+)\.layer(?P<layer>\d+)\.layer$")

_STANDARD_BLOCK_CONTRACTS = {
    **{block: (32, 128, 1) for block in (*range(0, 5), *range(66, 71))},
    **{block: (64, 224, 2) for block in (*range(5, 9), *range(62, 66))},
    **{block: (128, 384, 4) for block in (*range(9, 15), *range(56, 62))},
    **{block: (256, 704, 8) for block in (*range(15, 23), *range(48, 56))},
}
_DOWNSAMPLE_BLOCKS = {4, 8, 14, 22}
_UPSAMPLE_BLOCKS = {48, 56, 62, 66}
_STANDARD_PAYLOAD_SIZES = {
    32: {"regular": 0x50C0, "down": 0x58C0, "up": 0x5900},
    64: {"regular": 0xF140, "down": 0x11130, "up": 0x111A0},
    128: {"regular": 0x30240, "down": 0x38230, "up": 0x38320},
    256: {"regular": 0xA8450, "down": 0xC8440, "up": 0xC8630},
}

_QMMA_LOGICAL_ROW_SOURCE_16 = numpy.array(
    [0, 1, 4, 5, 8, 9, 12, 13, 2, 3, 6, 7, 10, 11, 14, 15],
    dtype=numpy.intp,
)


def unpack_qmma_e4m3_matrix(
    packed: bytes | numpy.ndarray,
    *,
    input_features: int,
    output_features: int,
    tile_order: str = "k-major",
) -> numpy.ndarray:
    """Undo the SM89 QMMA B-fragment packing into a [K, N] byte matrix."""
    if input_features <= 0 or input_features % 32:
        raise ValueError("input_features must be a positive multiple of 32")
    if output_features <= 0 or output_features % 32:
        raise ValueError("output_features must be a positive multiple of 32")

    source = numpy.frombuffer(packed, dtype=numpy.uint8).reshape(-1)
    expected_size = input_features * output_features
    if source.size != expected_size:
        raise ValueError(
            f"packed matrix size mismatch: expected {expected_size}, got {source.size}"
        )

    k_tiles = input_features // 32
    n_tiles = output_features // 32
    if tile_order == "k-major":
        physical_tiles = source.reshape(k_tiles, n_tiles, 2, 32, 2, 8)
    elif tile_order == "n128-major":
        if n_tiles % 4:
            raise ValueError("n128-major output features must be divisible by 128")
        physical_tiles = (
            source.reshape(n_tiles // 4, k_tiles, 4, 2, 32, 2, 8)
            .transpose(1, 0, 2, 3, 4, 5, 6)
            .reshape(k_tiles, n_tiles, 2, 32, 2, 8)
        )
    else:
        raise ValueError("tile_order must be k-major or n128-major")
    physical_values = physical_tiles.reshape(k_tiles, n_tiles, 32 * 32)

    physical_index = numpy.arange(32 * 32, dtype=numpy.intp)
    element = physical_index % 8
    fragment = (physical_index // 8) % 2
    lane = (physical_index // 16) % 32
    pair_group = physical_index // 512
    group_id = lane // 4
    thread_in_group = lane % 4
    k_index = thread_in_group * 4 + (element & 3) + (element >= 4) * 16
    n_index = (pair_group * 2 + fragment) * 8 + group_id

    logical_tiles = numpy.empty((k_tiles, n_tiles, 32, 32), dtype=numpy.uint8)
    logical_tiles[:, :, k_index, n_index] = physical_values
    fragment_logical = logical_tiles.transpose(0, 2, 1, 3).reshape(
        input_features, output_features
    )
    rows = numpy.arange(input_features, dtype=numpy.intp)
    logical_rows = rows - rows % 16 + _QMMA_LOGICAL_ROW_SOURCE_16[rows % 16]
    return fragment_logical[logical_rows]


def unpack_hmma_f16_matrix(
    packed: bytes | numpy.ndarray,
    *,
    input_features: int,
    output_features: int,
) -> numpy.ndarray:
    """Undo the HMMA.16816 B-fragment packing into a [K, N] f16 matrix."""
    if input_features != 16:
        raise ValueError("input_features must be 16 for HMMA.16816 packing")
    if output_features <= 0 or output_features % 16:
        raise ValueError("output_features must be a positive multiple of 16")

    if isinstance(packed, numpy.ndarray):
        source = numpy.frombuffer(packed.tobytes(), dtype="<f2")
    else:
        source = numpy.frombuffer(packed, dtype="<f2")
    expected_size = input_features * output_features
    if source.size != expected_size:
        raise ValueError(
            f"packed matrix size mismatch: expected {expected_size}, got {source.size}"
        )

    n_tiles = output_features // 16
    physical_values = source.reshape(n_tiles, 32 * 8)
    physical_index = numpy.arange(32 * 8, dtype=numpy.intp)
    element = physical_index % 8
    lane = physical_index // 8
    group_id = lane // 4
    thread_in_group = lane % 4
    fragment_element = element % 4
    k_index = thread_in_group * 2 + (fragment_element & 1) + (fragment_element >= 2) * 8
    n_index = group_id + (element >= 4) * 8

    logical_tiles = numpy.empty((n_tiles, 16, 16), dtype=numpy.float16)
    logical_tiles[:, k_index, n_index] = physical_values
    return logical_tiles.transpose(1, 0, 2).reshape(input_features, output_features)


def unpack_attention_bias(
    packed: bytes | numpy.ndarray,
    *,
    head_count: int,
) -> numpy.ndarray:
    """Decode physical 16x16 accumulator tiles into row-major 64x64 heads."""
    if head_count <= 0:
        raise ValueError("head_count must be positive")
    source = numpy.frombuffer(
        packed.tobytes() if isinstance(packed, numpy.ndarray) else packed,
        dtype="<f2",
    )
    if source.size != head_count * 64 * 64:
        raise ValueError("attention bias payload size mismatch")
    physical = source.reshape(head_count, 4, 4, 32, 8)
    tiles = numpy.empty((head_count, 4, 4, 16, 16), dtype=numpy.float16)
    for lane in range(32):
        group_id, thread_in_group = divmod(lane, 4)
        for element in range(8):
            fragment, fragment_element = divmod(element, 4)
            row = group_id + (8 if fragment_element >= 2 else 0)
            column = fragment * 8 + thread_in_group * 2 + (fragment_element & 1)
            tiles[..., row, column] = physical[..., lane, element]
    internal = tiles.transpose(0, 1, 3, 2, 4).reshape(head_count, 64, 64)
    internal_to_row_major = numpy.array(
        [
            y * 8 + x
            for tile_y in (0, 4)
            for tile_x in (0, 4)
            for y in range(tile_y, tile_y + 4)
            for x in range(tile_x, tile_x + 4)
        ],
        dtype=numpy.intp,
    )
    row_major_to_internal = numpy.argsort(internal_to_row_major)
    return numpy.ascontiguousarray(
        internal[:, row_major_to_internal][:, :, row_major_to_internal]
    )


def _e4m3_decode_table() -> numpy.ndarray:
    table = numpy.empty(256, dtype=numpy.float32)
    for encoded in range(256):
        exponent = (encoded >> 3) & 0xF
        mantissa = encoded & 0x7
        if exponent == 0xF and mantissa == 7:
            value = math.nan
        elif exponent == 0:
            value = mantissa * 2**-9
        else:
            value = math.ldexp(1.0 + mantissa * 0.125, exponent - 7)
        table[encoded] = math.copysign(value, -1.0 if encoded & 0x80 else 1.0)
    return table


_E4M3_DECODE_TABLE = _e4m3_decode_table()


def decode_e4m3(encoded: numpy.ndarray) -> numpy.ndarray:
    """Decode finite IEEE-like E4M3 bytes used by SM89 QMMA into float32."""
    return _E4M3_DECODE_TABLE[numpy.asarray(encoded, dtype=numpy.uint8)]


def _payload_bytes(payload: numpy.ndarray) -> numpy.ndarray:
    array = numpy.asarray(payload)
    if array.dtype != numpy.uint8 or array.ndim != 1:
        raise ValueError("packed payload must be a flat uint8 tensor")
    return array


def _require_size(name: str, payload: numpy.ndarray, expected: int) -> None:
    if payload.size != expected:
        raise ValueError(
            f"payload size mismatch for {name}: expected {expected}, got {payload.size}"
        )


def _require_zero(name: str, payload: numpy.ndarray, start: int, end: int) -> None:
    if numpy.any(payload[start:end]):
        raise ValueError(
            f"non-zero alignment bytes for {name} at [{start:#x}, {end:#x})"
        )


def _align(offset: int, alignment: int = 16) -> int:
    return (offset + alignment - 1) // alignment * alignment


def _qm_rows(size: int, power: int) -> numpy.ndarray:
    rows = numpy.arange(size, dtype=numpy.intp)
    permutation = rows - rows % 16 + _QMMA_LOGICAL_ROW_SOURCE_16[rows % 16]
    result = rows
    for _ in range(power):
        result = permutation[result]
    return result


def _semantic_qkv_weight(
    weight: numpy.ndarray,
    *,
    head_count: int,
) -> numpy.ndarray:
    channels, output_features = weight.shape
    if head_count <= 0 or channels % head_count or output_features != 3 * channels:
        raise ValueError("invalid head-interleaved QKV weight shape")
    head_channels = channels // head_count
    return numpy.ascontiguousarray(
        weight.reshape(channels, head_count, 3, head_channels)
        .transpose(0, 2, 1, 3)
        .reshape(channels, 3 * channels)
    )


def _unpack_split_feed_forward(
    raw: numpy.ndarray,
    *,
    prefix: str,
) -> dict[str, numpy.ndarray]:
    """Decode the split-family feed-forward core (blocks 23-30 and 40-47).

    The 512 KiB payload holds a 512x512 first projection followed by eight
    64x256 group expansion matrices and eight 256x64 group projection matrices
    (16 KiB k-major QMMA chunks each). The vendor ``ffwd_512_chained`` kernel
    computes ``e4m3(x @ first)`` and then, per 64-channel group, a
    ``64 -> 256 -> 64`` MLP with the quadratic-gate activation; the result is
    published as E4M3 before ``weight3`` (verified against DLL captures of the
    kernel output on every split block).
    """
    first_bytes = 512 * 512
    chunk_bytes = 64 * 256
    first = _matrix(
        raw,
        offset=0,
        input_features=512,
        output_features=512,
    )
    expand = numpy.stack(
        [
            _matrix(
                raw,
                offset=first_bytes + group * chunk_bytes,
                input_features=64,
                output_features=256,
            )
            for group in range(8)
        ]
    )
    project = numpy.stack(
        [
            _matrix(
                raw,
                offset=first_bytes + 8 * chunk_bytes + group * chunk_bytes,
                input_features=256,
                output_features=64,
            )
            for group in range(8)
        ]
    )
    return {
        f"{prefix}.first_projection_weight": numpy.ascontiguousarray(first),
        f"{prefix}.group_expand_weight": numpy.ascontiguousarray(expand),
        f"{prefix}.group_project_weight": numpy.ascontiguousarray(project),
    }


def _matrix(
    payload: numpy.ndarray,
    *,
    offset: int,
    input_features: int,
    output_features: int,
    tile_order: str = "k-major",
) -> numpy.ndarray:
    byte_count = input_features * output_features
    packed = payload[offset : offset + byte_count]
    logical = unpack_qmma_e4m3_matrix(
        packed,
        input_features=input_features,
        output_features=output_features,
        tile_order=tile_order,
    )
    return decode_e4m3(logical).astype(numpy.float16)


def _f16(payload: numpy.ndarray, offset: int, count: int) -> numpy.ndarray:
    end = offset + count * 2
    return numpy.frombuffer(payload[offset:end].tobytes(), dtype="<f2").copy()


def _f32(payload: numpy.ndarray, offset: int, count: int) -> numpy.ndarray:
    end = offset + count * 4
    return numpy.frombuffer(payload[offset:end].tobytes(), dtype="<f4").copy()


def _unpack_standard_swin(
    name: str,
    raw: numpy.ndarray,
    *,
    block: int,
    prefix: str,
) -> dict[str, numpy.ndarray]:
    channels, hidden_features, heads = _STANDARD_BLOCK_CONTRACTS[block]
    kind = (
        "down"
        if block in _DOWNSAMPLE_BLOCKS
        else "up"
        if block in _UPSAMPLE_BLOCKS
        else "regular"
    )

    if block == 0:
        _require_size(name, raw, 0x54C0)
    elif block == 70:
        _require_size(name, raw, 0x5530)
    else:
        _require_size(name, raw, _STANDARD_PAYLOAD_SIZES[channels][kind])

    tensors: dict[str, numpy.ndarray] = {}
    offset = 0
    if channels >= 64:
        channel_groups = channels // 32
        combined_output_features = 4 * channels + 128
        grouped = _matrix(
            raw,
            offset=offset,
            input_features=channels,
            output_features=combined_output_features,
            tile_order="n128-major",
        ).reshape(channels, 4 * channel_groups + 4, 32)
        tensors[f"{prefix}.ffn_expand_weight"] = numpy.stack(
            [
                numpy.stack(
                    [
                        numpy.stack(
                            [
                                grouped[
                                    input_group * 32 : (input_group + 1) * 32,
                                    output_head * 4 + branch,
                                ]
                                for input_group in range(channel_groups)
                            ]
                        )
                        for branch in range(4)
                    ]
                )
                for output_head in range(channel_groups)
            ]
        )
        tensors[f"{prefix}.ffn_branch_projection_weight"] = numpy.stack(
            [
                numpy.stack(
                    [
                        grouped[
                            output_head * 32 : (output_head + 1) * 32,
                            4 * channel_groups + branch,
                        ]
                        for branch in range(4)
                    ]
                )
                for output_head in range(channel_groups)
            ]
        )
        offset += channels * combined_output_features
        tensors[f"{prefix}.ffn_output_projection_weight"] = _matrix(
            raw,
            offset=offset,
            input_features=channels,
            output_features=channels,
        )
        offset += channels * channels
    else:
        tensors[f"{prefix}.weight1"] = _matrix(
            raw,
            offset=offset,
            input_features=channels,
            output_features=hidden_features,
        )
        offset += channels * hidden_features
        tensors[f"{prefix}.weight2"] = _matrix(
            raw,
            offset=offset,
            input_features=hidden_features,
            output_features=channels,
        )
        offset += hidden_features * channels

    if kind == "up":
        tensors[f"{prefix}.weight0"] = _matrix(
            raw,
            offset=offset,
            input_features=2 * channels,
            output_features=channels,
        )
        offset += 2 * channels * channels

    if kind != "up" or channels == 32:
        _require_zero(name, raw, offset, offset + 16)
        offset += 16
    if block == 0:
        adapter_bytes = 16 * channels * 2
        tensors[f"{prefix}.input_adapter_weight"] = unpack_hmma_f16_matrix(
            raw[offset : offset + adapter_bytes],
            input_features=16,
            output_features=channels,
        )
        offset += adapter_bytes
        tensors[f"{prefix}.ffn_cos_skip"] = _f16(raw, offset, channels)
        offset += channels * 2
        _require_zero(name, raw, offset, offset + 16)
        offset += 16
    else:
        tensors[f"{prefix}.ffn_cos_skip"] = _f16(raw, offset, channels)
        offset += channels * 2

    if block == 0:
        pass
    elif kind == "up":
        if channels == 32:
            _require_zero(name, raw, offset, offset + 16)
            offset += 16
        tensors[f"{prefix}.sin"] = _f16(raw, offset, channels)
        offset += channels * 2
    elif block == 70:
        rotation = _f16(raw, offset, 2 * channels)
        tensors[f"{prefix}.inp_merge_sin"] = rotation[:channels].copy()
        tensors[f"{prefix}.inp_merge_cos"] = rotation[channels:].copy()
        offset += 2 * channels * 2
    else:
        _require_zero(name, raw, offset, offset + 16)
        offset += 16

    qkv_weight = _matrix(
        raw,
        offset=offset,
        input_features=channels,
        output_features=3 * channels,
    )
    if channels >= 64:
        qkv_weight = _semantic_qkv_weight(qkv_weight, head_count=heads)
    tensors[f"{prefix}.qkv_weight"] = qkv_weight
    offset += 3 * channels * channels
    bias_count = heads * 64 * 64
    if channels >= 64:
        tensors[f"{prefix}.attn_bias"] = unpack_attention_bias(
            raw[offset : offset + bias_count * 2],
            head_count=heads,
        )
    else:
        tensors[f"{prefix}.attn_bias"] = _f16(raw, offset, bias_count).reshape(
            heads, 64, 64
        )
    offset += bias_count * 2
    tensors[f"{prefix}.attn_scale"] = _f32(raw, offset, heads)
    offset += heads * 4
    aligned = _align(offset)
    _require_zero(name, raw, offset, aligned)
    offset = aligned
    tensors[f"{prefix}.projection_weight"] = _matrix(
        raw,
        offset=offset,
        input_features=channels,
        output_features=channels,
    )
    offset += channels * channels
    tensors[f"{prefix}.attn_cos_skip"] = _f16(raw, offset, channels)
    offset += channels * 2

    if kind == "down":
        tensors[f"{prefix}.weight0"] = _matrix(
            raw,
            offset=offset,
            input_features=channels,
            output_features=2 * channels,
        )
        offset += 2 * channels * channels
        if offset != raw.size:
            _require_zero(name, raw, offset, raw.size)
            offset = raw.size
    elif block == 70:
        _require_zero(name, raw, offset, offset + 16)
        offset += 16
        for tensor_name in ("out_gain", "out_conv_weight"):
            physical_bytes = 16 * 16 * 2
            padded = unpack_hmma_f16_matrix(
                raw[offset : offset + physical_bytes],
                input_features=16,
                output_features=16,
            )
            if numpy.any(padded[:, 4:]):
                raise ValueError(
                    f"non-zero padded output channels for {name}.{tensor_name}"
                )
            tensors[f"{prefix}.{tensor_name}"] = padded[:, :4].copy()
            offset += physical_bytes
    else:
        _require_zero(name, raw, offset, offset + 16)
        offset += 16

    if offset != raw.size:
        raise ValueError(f"unconsumed payload bytes for {name}: {raw.size - offset}")
    return tensors


def unpack_known_tensor(name: str, payload: numpy.ndarray) -> dict[str, numpy.ndarray]:
    """Decode one proven packed tensor family or return an empty mapping."""
    if name == "block70.layer0.blend_scale":
        raw = _payload_bytes(payload)
        _require_size(name, raw, 2)
        return {name: _f16(raw, 0, 1)}

    match = _TENSOR_NAME.fullmatch(name)
    if match is None:
        return {}
    block = int(match.group("block"))
    layer = int(match.group("layer"))
    raw = _payload_bytes(payload)
    prefix = f"block{block}.layer{layer}"

    if layer == 0 and block in _STANDARD_BLOCK_CONTRACTS:
        return _unpack_standard_swin(name, raw, block=block, prefix=prefix)

    if block in {*range(23, 31), *range(40, 48)}:
        if layer == 0:
            matrix_bytes = 512 * 512
            _require_size(name, raw, matrix_bytes * 2)
            return _unpack_split_feed_forward(raw, prefix=prefix)
        if layer == 1:
            matrix_bytes = 512 * 512
            _require_size(name, raw, matrix_bytes + 512 * 2)
            return {
                f"{prefix}.weight3": _matrix(
                    raw, offset=0, input_features=512, output_features=512
                ),
                f"{prefix}.ffn_cos_skip": _f16(raw, matrix_bytes, 512),
            }
        if layer == 2:
            matrix_bytes = 512 * 1536
            bias_bytes = 16 * 64 * 64 * 2
            _require_size(name, raw, matrix_bytes + bias_bytes + 16 * 4)
            qkv_weight = _matrix(
                raw,
                offset=0,
                input_features=512,
                output_features=1536,
            )
            return {
                f"{prefix}.qkv_weight": _semantic_qkv_weight(
                    qkv_weight,
                    head_count=16,
                ),
                f"{prefix}.attn_bias": _f16(raw, matrix_bytes, 16 * 64 * 64).reshape(
                    16, 64, 64
                ),
                f"{prefix}.attn_scale": _f32(raw, matrix_bytes + bias_bytes, 16),
            }
        if layer == 3:
            matrix_bytes = 512 * 512
            _require_size(name, raw, matrix_bytes + 512 * 2)
            return {
                f"{prefix}.projection_weight": _matrix(
                    raw, offset=0, input_features=512, output_features=512
                ),
                f"{prefix}.attn_cos_skip": _f16(raw, matrix_bytes, 512),
            }
        if block == 30 and layer == 4:
            matrix_bytes = 512 * 1024
            _require_size(name, raw, matrix_bytes + 16)
            if numpy.any(raw[matrix_bytes:]):
                raise ValueError(f"non-zero alignment trailer for {name}")
            return {
                f"{prefix}.weight": _matrix(
                    raw, offset=0, input_features=512, output_features=1024
                )
            }

    if 31 <= block <= 38:
        if layer == 0:
            matrix_bytes = 1024 * 4096
            _require_size(name, raw, matrix_bytes + 16)
            if numpy.any(raw[matrix_bytes:]):
                raise ValueError(f"non-zero alignment trailer for {name}")
            return {
                f"{prefix}.weight": _matrix(
                    raw, offset=0, input_features=1024, output_features=4096
                )
            }
        if layer == 1:
            matrix_bytes = 4096 * 1024
            _require_size(name, raw, matrix_bytes + 1024 * 2)
            return {
                f"{prefix}.weight": _matrix(
                    raw, offset=0, input_features=4096, output_features=1024
                ),
                f"{prefix}.ffn_cos_skip": _f16(raw, matrix_bytes, 1024),
            }
        if layer == 2:
            scale_bytes = 32 * 4
            matrix_bytes = 1024 * 3072
            _require_size(name, raw, scale_bytes + matrix_bytes)
            qkv_weight = _matrix(
                raw,
                offset=scale_bytes,
                input_features=1024,
                output_features=3072,
            )
            return {
                f"{prefix}.attn_scale": _f32(raw, 0, 32),
                f"{prefix}.qkv_weight": _semantic_qkv_weight(
                    qkv_weight,
                    head_count=32,
                ),
            }
        if layer == 3:
            _require_size(name, raw, 2)
            return {f"{prefix}.attention_scalar": _f16(raw, 0, 1)}
        if layer == 4:
            matrix_bytes = 1024 * 1024
            _require_size(name, raw, matrix_bytes + 1024 * 2)
            return {
                f"{prefix}.projection_weight": _matrix(
                    raw, offset=0, input_features=1024, output_features=1024
                ),
                f"{prefix}.attn_cos_skip": _f16(raw, matrix_bytes, 1024),
            }

    if block == 39 and layer == 0:
        matrix_bytes = 1024 * 512
        _require_size(name, raw, matrix_bytes + 512 * 2)
        return {
            f"{prefix}.conv_weight": _matrix(
                raw, offset=0, input_features=1024, output_features=512
            ),
            f"{prefix}.inp_upsample_sin": _f16(raw, matrix_bytes, 512),
        }

    return {}


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _publish_staging(staging: pathlib.Path, destination: pathlib.Path) -> None:
    """Flush the staged file and publish it atomically (hard link, or rename where links are unavailable).

    The flush opens the file for writing: Windows rejects ``fsync`` on a read-only handle.
    """
    with open(staging, "r+b") as handle:
        os.fsync(handle.fileno())
    try:
        os.link(staging, destination)
    except (OSError, NotImplementedError):
        if destination.exists():
            raise
        os.replace(staging, destination)


def convert(source: pathlib.Path, destination: pathlib.Path) -> dict[str, object]:
    source = pathlib.Path(source)
    destination = pathlib.Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"destination already exists: {destination}")
    if not destination.parent.is_dir():
        raise FileNotFoundError(
            f"destination parent is not a directory: {destination.parent}"
        )

    decoded: dict[str, numpy.ndarray] = {}
    unsupported: list[str] = []
    with safe_open(source, framework="numpy") as handle:
        metadata = handle.metadata() or {}
        if metadata.get("format") != PACKED_FORMAT:
            raise ValueError(f"source format must be {PACKED_FORMAT}")
        source_names = list(handle.keys())
        for name in source_names:
            tensors = unpack_known_tensor(name, handle.get_tensor(name))
            if tensors:
                overlap = set(decoded).intersection(tensors)
                if overlap:
                    raise ValueError(f"duplicate decoded tensor: {sorted(overlap)[0]}")
                decoded.update(tensors)
            else:
                unsupported.append(name)
    if not decoded:
        raise ValueError("source contains no supported packed tensor families")

    opaque_output_names = sorted(
        name for name, value in decoded.items() if value.dtype == numpy.uint8
    )

    output_metadata = {
        "format": LOGICAL_FORMAT,
        "source_sha256": _sha256(source),
        "source_tensor_count": str(len(source_names)),
        "decoded_source_tensor_count": str(len(source_names) - len(unsupported)),
        "decoded_tensor_count": str(len(decoded)),
        "unsupported_source_tensors": json.dumps(sorted(unsupported)),
        "fully_logical": str(not opaque_output_names).lower(),
        "opaque_output_tensor_count": str(len(opaque_output_names)),
        "opaque_output_tensors": json.dumps(opaque_output_names),
        "matrix_contract": "K-by-N; output = input @ weight",
        "precision_contract": (
            "E4M3 matrices decoded to float16; HMMA F16 and proven "
            "scalar/vector dtypes preserved"
        ),
    }
    descriptor, staging_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    staging = pathlib.Path(staging_name)
    try:
        save_file(dict(sorted(decoded.items())), staging, metadata=output_metadata)
        _publish_staging(staging, destination)
    finally:
        staging.unlink(missing_ok=True)

    return {
        "schemaVersion": 1,
        "format": LOGICAL_FORMAT,
        "destination": str(destination),
        "sourceTensorCount": len(source_names),
        "decodedSourceTensorCount": len(source_names) - len(unsupported),
        "decodedTensorCount": len(decoded),
        "unsupportedSourceTensorCount": len(unsupported),
        "opaqueOutputTensorCount": len(opaque_output_names),
        "destinationSHA256": _sha256(destination),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Decode proven DLSSNR packed tensor families for ML inference."
    )
    parser.add_argument("source", type=pathlib.Path)
    parser.add_argument("destination", type=pathlib.Path)
    arguments = parser.parse_args()
    print(json.dumps(convert(arguments.source, arguments.destination), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
