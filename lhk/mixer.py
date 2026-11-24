"""Raise the microphone gain in /system/etc/mixer_paths.xml.

The displays listen through two digital mics (DMIC1 and DMIC2). The audio system
loads mixer_paths.xml and, while Kiosk Satellite listens, applies the path
speaker-stereo-dmic-ef-TERT_MI2S_TX, which includes speaker-dmic-endfire-TERT_MI2S_TX.
Stock sets no gain for them anywhere, so they record at 0 dB. Google's own app
did its own processing on top; without it, speech is about 20-25 dB too quiet.

This adds DEC1 and DEC2 Volume 108 (+24 dB; 84 is 0 dB) inside that one path, so
the gain is set each time the mics are switched on. On the 8" test display a
fixed tone went from -64 dB to -41 dB (2026-11-23). Every other byte is kept.
"""
from __future__ import annotations

import re

GAIN = 108          # +24 dB; the codec allows up to 124 (+40 dB)
PATH = "speaker-dmic-endfire-TERT_MI2S_TX"

_BLOCK = re.compile(rf'(<path name="{re.escape(PATH)}">\n)(.*?)(\n *</path>)', re.S)
_DEC = re.compile(r' *<ctl name="DEC[12] Volume" value="\d+" />\n')
_AFTER = re.compile(r'( *<ctl name="DEC2 MUX" value="DMIC2" />\n)')


class MixerPatchError(Exception):
    pass


def patch_mixer(xml: str) -> str:
    xml = xml.replace("\r\n", "\n")
    m = _BLOCK.search(xml)
    if not m or not _AFTER.search(m.group(2) + "\n"):
        raise MixerPatchError("The mixer file doesn't have the expected microphone path; not changing it.")
    body = _DEC.sub("", m.group(2) + "\n")
    gain = "".join(f'        <ctl name="DEC{n} Volume" value="{GAIN}" />\n' for n in (1, 2))
    body = _AFTER.sub(lambda a: a.group(1) + gain, body, count=1)
    return xml[:m.start()] + m.group(1) + body[:-1] + m.group(3) + xml[m.end():]


def is_patched(xml: str) -> bool:
    try:
        return patch_mixer(xml) == xml.replace("\r\n", "\n")
    except MixerPatchError:
        return False
