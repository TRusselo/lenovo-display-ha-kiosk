"""Speaker tuning: the amp's bass peak goes from Lenovo's +9 dB to +3 dB, and its 3-band compressor's
expander and compressor go flat (the limiter stays). ks-amp-tune.c carries the numbers; these tests hold
them to the design in lhk/amp.py."""
from __future__ import annotations

import cmath
import math
import re

import pytest

from lhk import amp
from lhk.downloads import _repo_file

SRC = _repo_file("assets/bootfix/amp/ks-amp-tune.c")


def _response(words, f, fs=48000):
    b0, b1, b2, a1, a2 = [(w - (1 << 32) if w >= 1 << 31 else w) / 2**31 for w in words]
    z = cmath.exp(-2j * math.pi * f / fs)
    return 20 * math.log10(abs((b0 + 2 * b1 * z + b2 * z * z) / (1 - 2 * a1 * z - a2 * z * z)))


def _c_bytes(name):
    m = re.search(rf"{name}\[\]\s*=\s*\{{(.*?)\}};", SRC.read_text(), re.S)
    assert m, name
    return [int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]{2})", m.group(1))]


def test_the_bass_peak_is_3_db_at_80_hz_and_flat_above():
    words = amp.bass_words(3.0)
    assert abs(_response(words, 79) - 3.0) < 0.1
    assert _response(words, 1000) == pytest.approx(0.0, abs=0.05)
    assert 1.0 < _response(words, 50) < 2.0


def test_lenovos_tunings_decode_to_the_bass_boost_we_replace():
    # The 8" runs one tuning (+9 dB at 79 Hz); an older Things app another (about +7 dB, 80-120 Hz).
    assert abs(_response(amp.STOCK_BASS[0], 79) - 8.9) < 0.2
    assert 6.0 < _response(amp.STOCK_BASS[1], 100) < 7.5


def test_the_tool_writes_the_designed_bass_filter():
    assert _c_bytes("BASS") == list(b"".join(w.to_bytes(4, "big") for w in amp.bass_words(amp.BASS_DB)))


def test_the_tool_only_acts_on_lenovos_tunings():
    # The second coefficient tells the tunings apart; any other value means leave the amp alone.
    sigs = _c_bytes("STOCK_SIG")
    assert [sigs[i:i + 4] for i in range(0, len(sigs), 4)] == [
        list(s[1].to_bytes(4, "big")) for s in amp.STOCK_BASS]
    assert _c_bytes("OURS_SIG") == list(amp.bass_words(amp.BASS_DB)[1].to_bytes(4, "big"))


def test_the_tool_flattens_expander_and_compressor_but_keeps_the_limiter():
    regs = _c_bytes("FLAT")          # page, register pairs: each starts a 4-byte word set to 0
    pairs = list(zip(regs[0::2], regs[1::2]))
    assert pairs == amp.FLAT_WORDS
    limiter = {(0x1b, 0x08), (0x1b, 0x30), (0x1b, 0x58)}     # k2 of each band
    assert not limiter & set(pairs)


def test_the_flattened_words_are_each_bands_expander_compressor_and_offset():
    names = {w: n for band in amp.DRC_BANDS for n, w in band.items()}
    assert sorted(names[w] for w in amp.FLAT_WORDS) == ["k0", "k0", "k0", "k1", "k1", "k1",
                                                          "off1", "off1", "off1"]


def test_the_tool_checks_the_layout_before_writing():
    # Each band's curve ends at 0 dB (off2 = 0) in both of Lenovo's tunings; anything else is a layout
    # we don't know, and the tool writes nothing.
    assert _c_bytes("OFF2") == [b for band in amp.DRC_BANDS for b in band["off2"]]


def test_releases_build_and_bundle_the_tool():
    jobs = _repo_file(".github/workflows/jar.yml").read_text()
    assert "ks-amp-tune.c" in jobs and "build/ks-amp-tune out/" in jobs   # staged next to the jar
    assert 'os.path.exists("ks-amp-tune")' in _repo_file("lhk.spec").read_text()
