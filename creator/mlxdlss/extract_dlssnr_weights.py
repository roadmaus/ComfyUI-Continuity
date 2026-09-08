#!/usr/bin/env python3
"""Extract the embedded DLSSNR WEIGHTS_HT resource as packed safetensors.

The NVIDIA DLL is always supplied by the user and is never copied into the
repository. Tensor names, serialized metadata, and payload bytes are preserved
exactly. The serialized tensors are backend-specific packed layer payloads, not
ordinary dense FP16 parameters, so safetensors stores them as flat U8 arrays.
Graph-derived shapes and mixed-precision segment boundaries are intentionally
not guessed by this tool.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import struct
import tempfile
from dataclasses import dataclass

import numpy
from safetensors.numpy import save_file


RESOURCE_NAME = "WEIGHTS_HT"
FORMAT_NAME = "dlssnr-WEIGHTS_HT-packed-u8-v2"
_RESOURCE_TYPE_RCDATA = 10
_PACKED_TENSOR_DTYPE_CODE = 1
_PACKED_TENSOR_ELEMENT_BYTES = 2


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_range(data: bytes, offset: int, size: int, context: str) -> None:
    if offset < 0 or size < 0 or offset > len(data) - size:
        raise ValueError(f"truncated {context}")


def _u16(data: bytes, offset: int, context: str) -> int:
    _require_range(data, offset, 2, context)
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int, context: str) -> int:
    _require_range(data, offset, 4, context)
    return struct.unpack_from("<I", data, offset)[0]


def _u64(data: bytes, offset: int, context: str) -> int:
    _require_range(data, offset, 8, context)
    return struct.unpack_from("<Q", data, offset)[0]


@dataclass(frozen=True)
class _PESection:
    virtual_address: int
    virtual_size: int
    raw_offset: int
    raw_size: int

    def file_offset(self, rva: int, size: int) -> int | None:
        span = max(self.virtual_size, self.raw_size)
        if rva < self.virtual_address or rva > self.virtual_address + span:
            return None
        relative = rva - self.virtual_address
        if relative > self.raw_size or size > self.raw_size - relative:
            return None
        return self.raw_offset + relative


@dataclass(frozen=True)
class SerializedWeight:
    payload: numpy.ndarray
    dtype_code: int
    metadata0: int
    metadata1: int
    dimensions: tuple[int, ...]

    def metadata(self) -> dict[str, object]:
        return {
            "byteCount": int(self.payload.size),
            "dtypeCode": self.dtype_code,
            "metadata0": self.metadata0,
            "metadata1": self.metadata1,
            "dimensions": list(self.dimensions),
        }


def _pe_sections(data: bytes) -> tuple[int, int, list[_PESection]]:
    if data[:2] != b"MZ":
        raise ValueError("source is not a PE file: missing MZ header")
    pe_offset = _u32(data, 0x3C, "DOS header")
    _require_range(data, pe_offset, 24, "PE header")
    if data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise ValueError("source is not a PE file: missing PE signature")

    coff_offset = pe_offset + 4
    section_count = _u16(data, coff_offset + 2, "COFF header")
    optional_size = _u16(data, coff_offset + 16, "COFF header")
    optional_offset = coff_offset + 20
    _require_range(data, optional_offset, optional_size, "optional header")
    if _u16(data, optional_offset, "optional header") != 0x20B:
        raise ValueError("DLSSNR extractor requires a PE32+ image")
    if optional_size < 112 + 3 * 8:
        raise ValueError("PE optional header has no resource directory")
    resource_rva = _u32(data, optional_offset + 112 + 2 * 8, "resource directory")
    resource_size = _u32(
        data, optional_offset + 112 + 2 * 8 + 4, "resource directory"
    )
    if resource_rva == 0 or resource_size == 0:
        raise ValueError("PE image has no resource directory")

    sections: list[_PESection] = []
    section_offset = optional_offset + optional_size
    for index in range(section_count):
        offset = section_offset + index * 40
        _require_range(data, offset, 40, "section table")
        sections.append(
            _PESection(
                virtual_size=_u32(data, offset + 8, "section table"),
                virtual_address=_u32(data, offset + 12, "section table"),
                raw_size=_u32(data, offset + 16, "section table"),
                raw_offset=_u32(data, offset + 20, "section table"),
            )
        )
    return resource_rva, resource_size, sections


def _rva_to_file_offset(
    sections: list[_PESection], rva: int, size: int, context: str
) -> int:
    for section in sections:
        if (offset := section.file_offset(rva, size)) is not None:
            return offset
    raise ValueError(f"{context} RVA is outside PE file-backed sections")


def extract_pe_resource(data: bytes, name: str = RESOURCE_NAME) -> bytes:
    resource_rva, resource_size, sections = _pe_sections(data)
    resource_offset = _rva_to_file_offset(
        sections, resource_rva, resource_size, "resource directory"
    )

    def resource_range(relative: int, size: int, context: str) -> int:
        if relative < 0 or size < 0 or relative > resource_size - size:
            raise ValueError(f"truncated {context}")
        absolute = resource_offset + relative
        _require_range(data, absolute, size, context)
        return absolute

    def entries(relative: int) -> list[tuple[int, int]]:
        directory = resource_range(relative, 16, "resource directory")
        count = _u16(data, directory + 12, "resource directory") + _u16(
            data, directory + 14, "resource directory"
        )
        table = resource_range(relative + 16, count * 8, "resource entries")
        return [
            (
                _u32(data, table + index * 8, "resource entry"),
                _u32(data, table + index * 8 + 4, "resource entry"),
            )
            for index in range(count)
        ]

    def resource_name(value: int) -> str | None:
        if not value & 0x8000_0000:
            return None
        relative = value & 0x7FFF_FFFF
        start = resource_range(relative, 2, "resource name")
        length = _u16(data, start, "resource name")
        text_start = resource_range(relative + 2, length * 2, "resource name")
        try:
            return data[text_start : text_start + length * 2].decode("utf-16-le")
        except UnicodeDecodeError as error:
            raise ValueError("resource name is not valid UTF-16LE") from error

    type_directory: int | None = None
    for identifier, target in entries(0):
        if identifier & 0x8000_0000:
            continue
        if identifier & 0xFFFF == _RESOURCE_TYPE_RCDATA:
            if not target & 0x8000_0000:
                raise ValueError("RCDATA resource entry is not a directory")
            type_directory = target & 0x7FFF_FFFF
            break
    if type_directory is None:
        raise ValueError("PE image has no RCDATA resource type")

    language_directory: int | None = None
    for identifier, target in entries(type_directory):
        if resource_name(identifier) == name:
            if not target & 0x8000_0000:
                raise ValueError(f"resource {name} entry is not a directory")
            language_directory = target & 0x7FFF_FFFF
            break
    if language_directory is None:
        raise ValueError(f"PE image has no {name} resource")

    language_entries = entries(language_directory)
    if len(language_entries) != 1:
        raise ValueError(f"resource {name} must have exactly one language entry")
    _, target = language_entries[0]
    if target & 0x8000_0000:
        raise ValueError(f"resource {name} language entry is unexpectedly a directory")
    data_entry = resource_range(target, 16, "resource data entry")
    payload_rva = _u32(data, data_entry, "resource data entry")
    payload_size = _u32(data, data_entry + 4, "resource data entry")
    payload_offset = _rva_to_file_offset(
        sections, payload_rva, payload_size, f"resource {name}"
    )
    _require_range(data, payload_offset, payload_size, f"resource {name}")
    return data[payload_offset : payload_offset + payload_size]


def parse_weight_map(data: bytes) -> dict[str, SerializedWeight]:
    if len(data) < 8:
        raise ValueError("truncated serialized weight map")
    declared_size = _u64(data, 0, "serialized weight map")
    if declared_size != len(data):
        raise ValueError(
            f"serialized map size mismatch: expected {declared_size}, got {len(data)}"
        )

    tensors: dict[str, SerializedWeight] = {}
    offset = 8
    while offset < len(data):
        name_length = _u64(data, offset, "tensor name length")
        offset += 8
        if name_length == 0 or name_length > 4_096:
            raise ValueError(f"invalid tensor name length: {name_length}")
        _require_range(data, offset, name_length, "tensor name")
        try:
            name = data[offset : offset + name_length].decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("tensor name is not valid UTF-8") from error
        offset += name_length
        if name in tensors:
            raise ValueError(f"duplicate tensor: {name}")

        outer_size = _u64(data, offset, f"{name} record size")
        offset += 8
        record_end = offset + outer_size
        _require_range(data, offset, outer_size, f"{name} record")
        if outer_size < 40:
            raise ValueError(f"record is too small for {name}")

        inner_size = _u64(data, offset, f"{name} inner size")
        offset += 8
        if inner_size != outer_size:
            raise ValueError(
                f"inner size mismatch for {name}: expected {outer_size}, got {inner_size}"
            )
        byte_count = _u64(data, offset, f"{name} byte count")
        offset += 8
        dtype_code = _u32(data, offset, f"{name} dtype")
        offset += 4
        if dtype_code != _PACKED_TENSOR_DTYPE_CODE:
            raise ValueError(f"unsupported dtype {dtype_code} for {name}")
        if byte_count > record_end - offset - 16:
            raise ValueError(f"truncated tensor data for {name}")
        tensor_data = data[offset : offset + byte_count]
        offset += byte_count

        if record_end - offset < 16:
            raise ValueError(f"truncated tensor metadata for {name}")
        metadata0 = _u32(data, offset, f"{name} metadata0")
        metadata1 = _u32(data, offset + 4, f"{name} metadata1")
        dimension_count = _u64(data, offset + 8, f"{name} dimension count")
        if dimension_count == 0 or dimension_count > 16:
            raise ValueError(f"invalid dimension count {dimension_count} for {name}")
        dimensions_size = dimension_count * 4
        if record_end - (offset + 16) != dimensions_size:
            raise ValueError(f"unexpected metadata size for {name}")
        dimensions = tuple(
            _u32(data, offset + 16 + index * 4, f"{name} dimension")
            for index in range(dimension_count)
        )
        offset = record_end
        element_count = 1
        for dimension in dimensions:
            if dimension == 0:
                raise ValueError(f"zero dimension for {name}")
            element_count *= dimension
        expected_bytes = element_count * _PACKED_TENSOR_ELEMENT_BYTES
        if byte_count != expected_bytes:
            raise ValueError(
                f"byte count mismatch for {name}: expected {expected_bytes}, got {byte_count}"
            )
        tensors[name] = SerializedWeight(
            payload=numpy.frombuffer(tensor_data, dtype=numpy.uint8).copy(),
            dtype_code=dtype_code,
            metadata0=metadata0,
            metadata1=metadata1,
            dimensions=dimensions,
        )

    if offset != len(data):
        raise ValueError("serialized weight map ended at an invalid offset")
    if not tensors:
        raise ValueError("serialized weight map contains no tensors")
    return tensors


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


def _write_safetensors(
    tensors: dict[str, SerializedWeight],
    destination: pathlib.Path,
    *,
    source_sha256: str,
    resource_sha256: str,
    source_kind: str,
) -> None:
    destination = pathlib.Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"destination already exists: {destination}")
    if not destination.parent.is_dir():
        raise FileNotFoundError(
            f"destination parent is not a directory: {destination.parent}"
        )
    payload_byte_count = sum(tensor.payload.size for tensor in tensors.values())
    source_tensor_records = {
        name: tensor.metadata() for name, tensor in sorted(tensors.items())
    }
    metadata = {
        "format": FORMAT_NAME,
        "source_kind": source_kind,
        "source_sha256": source_sha256,
        "resource_sha256": resource_sha256,
        "tensor_count": str(len(tensors)),
        "payload_byte_count": str(payload_byte_count),
        "payload_contract": "opaque backend-specific packed bytes; no dense dtype or shape is inferred",
        "source_tensor_records": json.dumps(
            source_tensor_records, separators=(",", ":"), sort_keys=True
        ),
    }
    descriptor, staging_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    os.close(descriptor)
    staging = pathlib.Path(staging_name)
    try:
        save_file(
            {
                name: tensor.payload
                for name, tensor in sorted(tensors.items())
            },
            staging,
            metadata=metadata,
        )
        _publish_staging(staging, destination)
    finally:
        staging.unlink(missing_ok=True)


def _summary(
    tensors: dict[str, SerializedWeight],
    destination: pathlib.Path,
    *,
    source_sha256: str,
    resource_sha256: str,
) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "format": FORMAT_NAME,
        "destination": str(destination),
        "sourceSHA256": source_sha256,
        "resourceSHA256": resource_sha256,
        "tensorCount": len(tensors),
        "payloadByteCount": sum(tensor.payload.size for tensor in tensors.values()),
        "storageDataType": "uint8",
        "sourceTensorDTypeCodes": sorted(
            {tensor.dtype_code for tensor in tensors.values()}
        ),
        "sourceShapes": "preserved in safetensors metadata",
        "payloadContract": "opaque backend-specific packed bytes",
    }


def extract_resource_blob(
    blob_path: pathlib.Path, destination: pathlib.Path
) -> dict[str, object]:
    blob_path = pathlib.Path(blob_path)
    destination = pathlib.Path(destination)
    resource = blob_path.read_bytes()
    digest = _sha256(resource)
    tensors = parse_weight_map(resource)
    _write_safetensors(
        tensors,
        destination,
        source_sha256=digest,
        resource_sha256=digest,
        source_kind="WEIGHTS_HT-resource-blob",
    )
    return _summary(
        tensors,
        destination,
        source_sha256=digest,
        resource_sha256=digest,
    )


def pe_file_version(data: bytes) -> str | None:
    """The PE VS_VERSION_INFO ``FileVersion`` string (``310,8,0,0`` style), if present."""
    key = "FileVersion".encode("utf-16-le") + b"\x00\x00"
    index = data.find(key)
    if index < 0:
        return None
    cursor = index + len(key)
    while cursor + 1 < len(data) and data[cursor : cursor + 2] == b"\x00\x00":
        cursor += 2
    characters = []
    while cursor + 1 < len(data):
        unit = data[cursor : cursor + 2]
        if unit == b"\x00\x00":
            break
        characters.append(unit)
        cursor += 2
    text = b"".join(characters).decode("utf-16-le", errors="ignore").strip()
    return text or None


def extract_dll(dll_path: pathlib.Path, destination: pathlib.Path) -> dict[str, object]:
    dll_path = pathlib.Path(dll_path)
    destination = pathlib.Path(destination)
    dll = dll_path.read_bytes()
    file_version = pe_file_version(dll)
    resource = extract_pe_resource(dll)
    tensors = parse_weight_map(resource)
    dll_digest = _sha256(dll)
    resource_digest = _sha256(resource)
    _write_safetensors(
        tensors,
        destination,
        source_sha256=dll_digest,
        resource_sha256=resource_digest,
        source_kind="nvngx_dlssnr.dll",
    )
    summary = _summary(
        tensors,
        destination,
        source_sha256=dll_digest,
        resource_sha256=resource_digest,
    )
    summary["fileVersion"] = file_version
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract an external nvngx_dlssnr.dll WEIGHTS_HT resource to safetensors."
    )
    parser.add_argument("source", type=pathlib.Path)
    parser.add_argument("destination", type=pathlib.Path)
    parser.add_argument(
        "--resource-blob",
        action="store_true",
        help="treat source as an already extracted WEIGHTS_HT resource",
    )
    arguments = parser.parse_args()
    summary = (
        extract_resource_blob(arguments.source, arguments.destination)
        if arguments.resource_blob
        else extract_dll(arguments.source, arguments.destination)
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
