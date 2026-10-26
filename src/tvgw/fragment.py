"""Wire framing, fragmentation, and reassembly."""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from typing import Dict, Tuple

HEADER = struct.Struct(">BBHBBHI")
CRC_POLY = 0x1021


class PayloadTooLargeError(ValueError):
    pass


def crc16_ccitt_false(data: bytes, init: int = 0xFFFF) -> int:
    crc = init
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ CRC_POLY) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


@dataclass
class WireFrame:
    version_flags: int
    profile_flags: int
    msg_seq: int
    frag_idx: int
    frag_total: int
    payload_len: int
    msg_crc32: int
    payload: bytes

    def pack(self) -> bytes:
        header = HEADER.pack(
            self.version_flags,
            self.profile_flags,
            self.msg_seq,
            self.frag_idx,
            self.frag_total,
            self.payload_len,
            self.msg_crc32,
        )
        body = header + self.payload
        crc = crc16_ccitt_false(body)
        return body + struct.pack(">H", crc)

    @staticmethod
    def unpack(data: bytes, mtu: int = 160) -> "WireFrame":
        if len(data) < 14:
            raise ValueError("frame too short")
        body, crc_bytes = data[:-2], data[-2:]
        expected = struct.unpack(">H", crc_bytes)[0]
        if crc16_ccitt_false(body) != expected:
            raise ValueError("crc16 mismatch")
        fields = HEADER.unpack(body[:12])
        payload = body[12:]
        if len(payload) != fields[5]:
            raise ValueError("payload length mismatch")
        return WireFrame(*fields, payload)


def fragment_payload(
    payload: bytes,
    msg_seq: int,
    profile_flags: int,
    priority: int,
    epoch: int,
    mtu: int = 160,
    max_frags: int = 32,
) -> list[bytes]:
    if len(payload) == 0:
        raise ValueError("empty payload")
    max_payload = mtu - 14
    if max_payload < 1:
        raise ValueError("mtu too small")
    chunks = [payload[i : i + max_payload] for i in range(0, len(payload), max_payload)]
    if not chunks:
        chunks = [b""]
    if len(chunks) > max_frags:
        raise PayloadTooLargeError("too many fragments")
    msg_crc = zlib.crc32(payload) & 0xFFFFFFFF
    version = 0x40 | (epoch << 2) | (priority & 0x3)
    frames: list[bytes] = []
    total = len(chunks)
    for idx, chunk in enumerate(chunks):
        if len(chunk) == 0 and total > 1:
            raise ValueError("empty payload slice")
        if len(chunk) == 0 and total == 1:
            chunk = payload or b"\x00"
        wf = WireFrame(
            version_flags=version,
            profile_flags=profile_flags,
            msg_seq=msg_seq,
            frag_idx=idx,
            frag_total=total,
            payload_len=len(chunk),
            msg_crc32=msg_crc,
            payload=chunk,
        )
        frames.append(wf.pack())
    return frames


def build_ack_frame(
    msg_seq: int,
    frag_total: int,
    bitmap: int,
    priority: int,
    epoch: int,
    profile_flags: int = 0,
) -> bytes:
    version = 0x60 | (epoch << 2) | (priority & 0x3)  # is_ack bit
    payload = struct.pack("<I", bitmap & 0xFFFFFFFF)
    wf = WireFrame(
        version_flags=version,
        profile_flags=profile_flags,
        msg_seq=msg_seq,
        frag_idx=0,
        frag_total=frag_total,
        payload_len=4,
        msg_crc32=0,
        payload=payload,
    )
    return wf.pack()


@dataclass
class Reassembler:
    max_assemblies: int = 64
    max_buffer_bytes: int = 64 * 1024
    max_payload: int = 1 << 20
    inactivity_s: float = 600.0

    assemblies: Dict[Tuple[int, int], dict] = field(default_factory=dict)
    buffer_bytes: int = 0
    protocol_mismatch_errors: int = 0
    conflict_errors: int = 0

    def ingest(self, frame: WireFrame, now_s: float) -> bytes | None:
        if frame.frag_total == 0 or frame.frag_total > 32 or frame.frag_idx >= frame.frag_total:
            raise ValueError("invalid fragment indices")
        key = ((frame.version_flags >> 2) & 0x7, frame.msg_seq)
        asm = self.assemblies.get(key)
        if asm is None:
            if len(self.assemblies) >= self.max_assemblies:
                self._evict_oldest()
            asm = {
                "frags": {},
                "total": frame.frag_total,
                "profile": frame.profile_flags,
                "crc32": frame.msg_crc32,
                "last": now_s,
            }
            self.assemblies[key] = asm
        else:
            if (
                asm["total"] != frame.frag_total
                or asm["profile"] != frame.profile_flags
                or asm["crc32"] != frame.msg_crc32
            ):
                self.protocol_mismatch_errors += 1
                return None
        if frame.frag_idx in asm["frags"]:
            if asm["frags"][frame.frag_idx] != frame.payload:
                self.conflict_errors += 1
            return None
        asm["frags"][frame.frag_idx] = frame.payload
        asm["last"] = now_s
        self.buffer_bytes += len(frame.payload)
        if self.buffer_bytes > self.max_buffer_bytes:
            self._evict_oldest()
        if len(asm["frags"]) == asm["total"]:
            ordered = b"".join(asm["frags"][i] for i in range(asm["total"]))
            if len(ordered) > self.max_payload:
                del self.assemblies[key]
                return None
            if (zlib.crc32(ordered) & 0xFFFFFFFF) != asm["crc32"]:
                return None
            del self.assemblies[key]
            self.buffer_bytes = max(0, self.buffer_bytes - len(ordered))
            return ordered
        return None

    def _evict_oldest(self) -> None:
        if not self.assemblies:
            return
        key = min(self.assemblies, key=lambda k: self.assemblies[k]["last"])
        freed = sum(len(v) for v in self.assemblies[key]["frags"].values())
        del self.assemblies[key]
        self.buffer_bytes = max(0, self.buffer_bytes - freed)
