"""Speaker tuning for the TI TAS5825M amp.

Lenovo's Things app (sparrow.oem) loads a TI tuning into the amp once at boot, over I2C (bus I2C1, address
0x49): DSP coefficients in book 0x8C. It boosts the bass by about +9 dB at 79 Hz and runs a 3-band
compressor, where each band has an expander that pushes quiet sound down, a compressor, and a limiter at the
top. Thunder lost its bass, rain faded, and loud bass rattled the speaker (2026-11-16 and 2026-11-23).

ks-amp-tune (assets/bootfix/amp) rewrites two things after Lenovo's load, at every boot:
- the bass peak, to +3 dB at the same 79 Hz and width. More bass is up to Kiosk Satellite's equalizer;
- each band's expander slope (k0), compressor slope (k1) and the gain where they meet (off1), to 0. Below
  the limiter threshold the sound then passes unchanged. The limiter (k2) stays: it protects the speaker.

The DRC layout matches TI's process flows note (SLAA786A): per band, energy, attack and decay time
constants (1.31), then k0, k1, k2, T1, T2, off1, off2 (9.23). Both tunings Lenovo shipped decode
consistently: each curve returns to 0 dB at T2 (off2 = 0). This module holds the numbers; the C tool
carries a copy, which tests/test_amp.py checks.
"""
from __future__ import annotations

import math

BASS_DB = 3.0
BASS_HZ, BASS_Q, FS = 78.8, 1.1, 48000      # fitted from Lenovo's filter (book 0x8C page 0x16, 0x1C-0x2F)

# Lenovo's bass filter words (b0, b1/2, b2, -a1/2, -a2; 1.31), per Things app version.
STOCK_BASS = [
    (0x7FFFFFFF, 0x8102323F, 0x7DFEE90B, 0x7FA2DA3D, 0x80B6F9B0),   # the 8" today: +9 dB at 79 Hz
    (0x7FFFFFFF, 0x83A7A5D4, 0x78B628C5, 0x7E55D6C8, 0x834EC7A9),   # an older app: about +7 dB, 80-120 Hz
]


def _word(page: int, reg: int, n: int) -> tuple[int, int]:
    """The n-th 4-byte word after (page, reg); a page holds words at 0x08-0x7C."""
    reg += 4 * n
    while reg > 0x7C:
        page, reg = page + 1, reg - 0x78
    return page, reg


_NAMES = ["energy", "attack", "decay", "k0", "k1", "k2", "T1", "T2", "off1", "off2"]
DRC_BANDS = [{name: _word(p, r, i) for i, name in enumerate(_NAMES)}
             for p, r in ((0x1A, 0x6C), (0x1B, 0x1C), (0x1B, 0x44))]
FLAT_WORDS = [band[n] for band in DRC_BANDS for n in ("k0", "k1", "off1")]
FLAT_WORDS.sort()


def bass_words(db: float) -> list[int]:
    """A peaking filter at Lenovo's frequency and width, stored the way the amp wants it."""
    a = 10 ** (db / 40)
    w = 2 * math.pi * BASS_HZ / FS
    alpha = math.sin(w) / (2 * BASS_Q)
    a0 = 1 + alpha / a
    b = [(1 + alpha * a) / a0, -2 * math.cos(w) / a0, (1 - alpha * a) / a0]
    a1, a2 = -2 * math.cos(w) / a0, (1 - alpha / a) / a0
    k = (1 - 2**-31) / b[0]                 # b0 must fit in 1.31; the 0.03 dB this costs doesn't matter
    vals = [b[0] * k, b[1] * k / 2, b[2] * k, -a1 / 2, -a2]
    return [max(-2**31, min(2**31 - 1, round(v * 2**31))) & 0xFFFFFFFF for v in vals]
