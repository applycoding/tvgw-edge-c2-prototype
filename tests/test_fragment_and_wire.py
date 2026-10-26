import zlib

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tvgw.fragment import (
    PayloadTooLargeError,
    Reassembler,
    WireFrame,
    build_ack_frame,
    crc16_ccitt_false,
    fragment_payload,
)


def test_golden_vector_test_payload():
    payload = b"TEST"
    msg_crc = zlib.crc32(payload) & 0xFFFFFFFF
    wf = WireFrame(0x40, 0x04, 1, 0, 1, 4, msg_crc, payload)
    frame = wf.pack()
    assert len(frame) == 4 + 14
    assert WireFrame.unpack(frame).payload == payload


def test_crc16_known():
    assert crc16_ccitt_false(b"123456789") == 0x29B1


def test_ack_frame_18_bytes():
    ack = build_ack_frame(1, 3, 0b111, 0, 0, 0x04)
    assert len(ack) == 18


def test_reject_bad_frag_total():
    with pytest.raises(ValueError):
        WireFrame.unpack(fragment_payload(b"x", 1, 1, 0, 0, mtu=160)[0].replace(bytes([1]), bytes([99]), 1))


def test_payload_too_many_frags():
    big = b"x" * 5000
    with pytest.raises(PayloadTooLargeError):
        fragment_payload(big, 1, 1, 0, 0, mtu=160, max_frags=32)


def test_reassembler_complete():
    payload = b"hello-world-payload"
    frames = fragment_payload(payload, 7, 0x04, 1, 0, mtu=160)
    r = Reassembler()
    out = None
    for i, fr in enumerate(frames):
        out = r.ingest(WireFrame.unpack(fr), float(i))
    assert out == payload


def test_conflicting_duplicate_fragment():
    payload = b"a" * 300
    frames = fragment_payload(payload, 1, 1, 0, 0, mtu=160)
    r = Reassembler()
    r.ingest(WireFrame.unpack(frames[0]), 0.0)
    wf = WireFrame.unpack(frames[0])
    wf.payload = b"z" * len(wf.payload)
    frame2 = wf.pack()
    r.ingest(WireFrame.unpack(frame2), 0.1)
    assert r.conflict_errors >= 1


def test_reassembly_bounds_eviction():
    r = Reassembler(max_assemblies=2, max_buffer_bytes=32)
    for seq in range(5):
        fr = fragment_payload(b"x", seq, 1, 0, 0, mtu=160)[0]
        r.ingest(WireFrame.unpack(fr), 0.0)
    assert len(r.assemblies) <= 2


@given(st.binary(min_size=1, max_size=200))
def test_fragment_roundtrip(data):
    frames = fragment_payload(data, 3, 2, 1, 0, mtu=200)
    r = Reassembler()
    got = None
    for fr in frames:
        got = r.ingest(WireFrame.unpack(fr), 0.0)
    assert got == data


def test_zero_payload_data_rejected():
    with pytest.raises(ValueError):
        fragment_payload(b"", 1, 1, 0, 0, mtu=160)
