"""Old 2018 bootloaders (GitHub issues 6 and 7): a vbmeta their libavb 1.0 accepts."""
import hashlib
import struct

import pytest

from lhk import vbmeta


# --- a small, independent vbmeta writer, so the tests don't check the module against itself ---

def _hash_desc(name: bytes, digest_len=32, flags=0, salt_len=32, size=4096):
    body = struct.pack(">Q32sIIII60s", size, b"sha256", len(name), salt_len, digest_len, flags, b"")
    body += name + b"s" * salt_len + b"d" * digest_len
    body += b"\0" * (-len(body) % 8)
    return struct.pack(">QQ", 2, len(body)) + body


def _tree_desc(name: bytes):
    body = struct.pack(">IQQQIIIQQ32sIIII60s", 1, 1 << 20, 1 << 20, 8192, 4096, 4096, 0, 0, 0,
                       b"sha1", len(name), 32, 20, 0, b"")
    body += name + b"s" * 32 + b"r" * 20
    body += b"\0" * (-len(body) % 8)
    return struct.pack(">QQ", 1, len(body)) + body


def _cmdline_desc(text: bytes):
    body = struct.pack(">II", 1, len(text)) + text
    body += b"\0" * (-len(body) % 8)
    return struct.pack(">QQ", 3, len(body)) + body


DESCS = [_cmdline_desc(b"dm=verity"), _hash_desc(b"boot"),
         _hash_desc(b"factory", digest_len=0, flags=1, salt_len=0),
         _hash_desc(b"oem_bootloader"), _tree_desc(b"system"), _tree_desc(b"vendor")]


def _stock_like():
    """Shaped like the userdebug vbmeta_a: libavb 1.1, SHA512_RSA4096, flags 1, rollback 3."""
    descs = b"".join(DESCS)
    pk = b"P" * 1032
    meta = b"M" * 100
    aux = descs + pk + meta
    aux += b"\0" * (-len(aux) % 64)
    auth = b"\0" * 576
    header = struct.pack(">4sIIQQIQQQQQQQQQQQII", b"AVB0", 1, 1, len(auth), len(aux), 5,
                         0, 64, 64, 512, len(descs), len(pk), len(descs) + len(pk), len(meta),
                         0, len(descs), 3, 1, 0)
    header += b"avbtool 1.2.0".ljust(48, b"\0")
    header += b"\0" * (256 - len(header))
    return header + auth + aux + b"\0" * 4096       # a partition read is padded


@pytest.fixture(scope="module")
def key():
    return vbmeta.new_key(bits=1024)   # small for speed; the real one is 4096-bit


def test_old_bootloader_is_told_by_its_missing_persistent_digest_support():
    assert vbmeta.supports_avb_1_1(b"...platform/msm_shared/avb/libavb...avb.persistent_digest.\0...")
    assert not vbmeta.supports_avb_1_1(b"...platform/msm_shared/avb/libavb/avb_slot_verify.c...")


def test_old_bootloader_vbmeta_drops_only_factory_and_oem_bootloader(key):
    out = vbmeta.for_old_bootloader(_stock_like(), key=key)
    descs = vbmeta.descriptors(out)
    assert [d.name for d in descs if d.name] == [b"boot", b"system", b"vendor"]
    assert [d.raw for d in descs] == [DESCS[i] for i in (0, 1, 4, 5)]     # byte-identical


def test_old_bootloader_vbmeta_needs_only_libavb_1_0_and_keeps_the_header(key):
    h = vbmeta.header(vbmeta.for_old_bootloader(_stock_like(), key=key))
    assert (h.major, h.minor) == (1, 0)
    assert (h.flags, h.rollback_index, h.algorithm) == (1, 3, 5)


def test_old_bootloader_vbmeta_turns_verity_off(key):
    # The userdebug image ships with flags 0; fvsqr's working vbmeta had verity off (flag 1).
    stock = bytearray(_stock_like())
    stock[120:124] = struct.pack(">I", 0)
    assert vbmeta.header(vbmeta.for_old_bootloader(bytes(stock), key=key)).flags == 1


def test_old_bootloader_vbmeta_is_signed_by_the_key_it_carries(key):
    out = vbmeta.for_old_bootloader(_stock_like(), key=key)
    h = vbmeta.header(out)
    auth = out[256:256 + h.auth_size]
    aux = out[256 + h.auth_size:256 + h.auth_size + h.aux_size]
    assert h.auth_size % 64 == 0 and h.aux_size % 64 == 0
    digest = hashlib.sha512(out[:256] + aux).digest()
    assert auth[h.hash_offset:h.hash_offset + h.hash_size] == digest
    pk = aux[h.public_key_offset:h.public_key_offset + h.public_key_size]
    bits = struct.unpack(">I", pk[:4])[0]
    n = int.from_bytes(pk[8:8 + bits // 8], "big")
    assert n == key.n
    sig = int.from_bytes(auth[h.signature_offset:h.signature_offset + h.signature_size], "big")
    em = pow(sig, 65537, n).to_bytes(bits // 8, "big")
    assert em.startswith(b"\0\x01\xff") and em.endswith(vbmeta.SHA512_DIGEST_INFO + digest)
    # n0inv and rr, as libavb's RSA code expects them
    n0inv = struct.unpack(">I", pk[4:8])[0]
    assert (n * n0inv) % (1 << 32) == (1 << 32) - 1
    assert int.from_bytes(pk[8 + bits // 8:8 + bits // 4], "big") == pow(2, 2 * bits, n)


def test_a_vbmeta_without_those_entries_is_refused(key):
    stripped = vbmeta.for_old_bootloader(_stock_like(), key=key)
    with pytest.raises(ValueError):
        vbmeta.for_old_bootloader(stripped, key=key)


def test_not_a_vbmeta_is_refused(key):
    with pytest.raises(ValueError):
        vbmeta.for_old_bootloader(b"ANDROID!" + b"\0" * 300, key=key)
