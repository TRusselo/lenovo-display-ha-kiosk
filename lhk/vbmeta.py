"""A vbmeta_a that Lenovo's original 2018 bootloader accepts (GitHub issues 6 and 7).

Displays that never got Lenovo's final update still run a bootloader with
libavb 1.0. The userdebug vbmeta_a needs libavb 1.1 because of two entries:
`factory` (a persistent digest: no digest, flag 1) and `oem_bootloader`.
libavb 1.0 rejects the whole vbmeta for that, even with verified boot
unlocked, so slot A never starts and the display goes back to slot B.

for_old_bootloader() drops just those two entries, keeps every other one
byte-identical, keeps the rollback index (3), turns verity off (flag 1),
asks for libavb 1.0, and signs with a throwaway key made for this run. With verified
boot unlocked, the bootloader accepts any key. This is what fvsqr built by
hand with avbtool, and slot A then started (issue 6).

Pure Python, after libavb's documented format, so it runs the same on every
computer without avbtool or openssl.
"""
from __future__ import annotations

import hashlib
import secrets
import struct
from dataclasses import dataclass

# libavb 1.1 reads persistent digests from "avb.persistent_digest.<partition>"; 1.0 can't.
PERSISTENT_DIGEST = b"avb.persistent_digest."
DROP = {b"factory", b"oem_bootloader"}
SHA512_RSA4096 = 5
# Verity off, as in the vbmeta that started on fvsqr's display; RootStep's disable-verity
# sets the same flag on every display later anyway.
HASHTREE_DISABLED = 1
SHA512_DIGEST_INFO = bytes.fromhex("3051300d060960864801650304020305000440")
RELEASE = b"lhk: for libavb 1.0 bootloaders"

_HEADER = ">4sIIQQIQQQQQQQQQQQII"      # the first 128 bytes; then a 48-byte release string


def supports_avb_1_1(aboot: bytes) -> bool:
    """Does this bootloader (aboot) image accept the userdebug vbmeta as it is?"""
    return PERSISTENT_DIGEST in aboot


@dataclass
class Header:
    major: int
    minor: int
    auth_size: int
    aux_size: int
    algorithm: int
    hash_offset: int
    hash_size: int
    signature_offset: int
    signature_size: int
    public_key_offset: int
    public_key_size: int
    metadata_offset: int
    metadata_size: int
    descriptors_offset: int
    descriptors_size: int
    rollback_index: int
    flags: int
    rollback_index_location: int


@dataclass
class Descriptor:
    tag: int
    name: bytes
    raw: bytes


def header(blob: bytes) -> Header:
    if len(blob) < 256 or blob[:4] != b"AVB0":
        raise ValueError("not a vbmeta image")
    return Header(*struct.unpack(_HEADER, blob[:128])[1:])


def _aux(blob: bytes, h: Header) -> bytes:
    return blob[256 + h.auth_size:256 + h.auth_size + h.aux_size]


def descriptors(blob: bytes) -> list[Descriptor]:
    h = header(blob)
    data = _aux(blob, h)[h.descriptors_offset:h.descriptors_offset + h.descriptors_size]
    out, i = [], 0
    while i < len(data):
        tag, length = struct.unpack(">QQ", data[i:i + 16])
        raw = data[i:i + 16 + length]
        body = raw[16:]
        name = b""
        if tag == 2:        # hash: image_size, algorithm[32], name_len, ...
            n = struct.unpack(">I", body[40:44])[0]
            name = body[116:116 + n]
        elif tag == 1:      # hashtree
            n = struct.unpack(">I", body[88:92])[0]
            name = body[164:164 + n]
        out.append(Descriptor(tag, name, raw))
        i += 16 + length
    return out


# --- RSA, as libavb wants it ------------------------------------------------------------------

@dataclass
class Key:
    n: int
    d: int
    bits: int
    e: int = 65537


def _probably_prime(n: int) -> bool:
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    r, s = n - 1, 0
    while r % 2 == 0:
        r //= 2
        s += 1
    for _ in range(40):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, r, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _prime(bits: int, e: int) -> int:
    while True:
        p = secrets.randbits(bits) | (3 << (bits - 2)) | 1     # top two bits: n gets all its bits
        if p % e != 1 and _probably_prime(p):
            return p


def new_key(bits: int = 4096) -> Key:
    """A throwaway key. Never saved: only an unlocked bootloader takes it, and it accepts any."""
    e = 65537
    while True:
        p, q = _prime(bits // 2, e), _prime(bits // 2, e)
        n = p * q
        if p != q and n.bit_length() == bits:
            return Key(n=n, d=pow(e, -1, (p - 1) * (q - 1)), bits=bits)


def _public_key_blob(key: Key) -> bytes:
    n0inv = (1 << 32) - pow(key.n, -1, 1 << 32)
    rr = pow(2, 2 * key.bits, key.n)
    size = key.bits // 8
    return struct.pack(">II", key.bits, n0inv) + key.n.to_bytes(size, "big") + rr.to_bytes(size, "big")


def _sign(key: Key, digest: bytes) -> bytes:
    size = key.bits // 8
    t = SHA512_DIGEST_INFO + digest
    em = b"\0\x01" + b"\xff" * (size - len(t) - 3) + b"\0" + t
    return pow(int.from_bytes(em, "big"), key.d, key.n).to_bytes(size, "big")


def _pad64(b: bytes) -> bytes:
    return b + b"\0" * (-len(b) % 64)


def for_old_bootloader(blob: bytes, key: Key | None = None) -> bytes:
    h = header(blob)
    descs = descriptors(blob)
    kept = [d for d in descs if not (d.tag == 2 and d.name in DROP)]
    if len(kept) == len(descs):
        raise ValueError("this vbmeta has no factory or oem_bootloader entry to drop")
    key = key or new_key()
    sig_size = key.bits // 8
    desc_bytes = b"".join(d.raw for d in kept)
    pk = _public_key_blob(key)
    aux = _pad64(desc_bytes + pk)
    auth_size = len(_pad64(b"\0" * (64 + sig_size)))
    head = struct.pack(_HEADER, b"AVB0", 1, 0, auth_size, len(aux), SHA512_RSA4096,
                       0, 64, 64, sig_size,
                       len(desc_bytes), len(pk), len(desc_bytes) + len(pk), 0,
                       0, len(desc_bytes), h.rollback_index, h.flags | HASHTREE_DISABLED,
                       h.rollback_index_location)
    head = (head + RELEASE.ljust(48, b"\0")).ljust(256, b"\0")
    digest = hashlib.sha512(head + aux).digest()
    auth = (digest + _sign(key, digest)).ljust(auth_size, b"\0")
    return head + auth + aux
