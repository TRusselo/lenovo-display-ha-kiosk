"""Raise the analog mic gain in mixer_paths_openq624_fep.xml.

Stock leaves the mic ~20-30 dB too quiet without Google's own processing.
The exact change proven on two displays:
  - top-level defaults: DEC1/DEC2 Volume 84 -> 96
  - inside <path> blocks: ADC1/ADC2/ADC3 Volume 6 -> 12
The top-level ADC defaults (4) stay as they are. Every other byte is kept.
"""
from __future__ import annotations

import re

_DEC = re.compile(r'(<ctl name="DEC[12] Volume" value=")84(" />)')
_ADC = re.compile(r'(<ctl name="ADC[123] Volume" value=")6(" />)')
_DEC_DONE = re.compile(r'<ctl name="DEC[12] Volume" value="96" />')
_ADC_DONE = re.compile(r'<ctl name="ADC[123] Volume" value="12" />')


class MixerPatchError(Exception):
    pass


def patch_mixer(xml: str) -> str:
    first_path = xml.find("<path ")
    if first_path < 0:
        raise MixerPatchError("This doesn't look like the expected mixer file (no <path> blocks).")
    top, paths = xml[:first_path], xml[first_path:]
    top = _DEC.sub(r"\g<1>96\g<2>", top)
    paths = _ADC.sub(r"\g<1>12\g<2>", paths)
    if not _DEC_DONE.search(top) or not _ADC_DONE.search(paths):
        raise MixerPatchError("The mixer file doesn't contain the expected mic settings; not changing it.")
    return top + paths
