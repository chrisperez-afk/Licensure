"""
Consistent Last, First display regardless of which source a name came
from — DSHS gives ALL CAPS ("CARTER, CONRAD WESLEY"), NREMT and the
shift roster give Title Case ("Alarcon, Larissa"), and manual entry could
be anything. Plain title-casing gets most names right; the handful of
patterns below (Mc/Mac, apostrophes, and name suffixes) are the common
cases plain title-casing gets wrong.
"""

import re

_SUFFIX_CASING = {"jr": "Jr", "sr": "Sr", "ii": "II", "iii": "III", "iv": "IV", "v": "V"}

_MC_RE = re.compile(r"^mc(.)(.*)$")
_MAC_RE = re.compile(r"^mac(.)(.*)$")


def _cap_word(word):
    if not word:
        return word
    lower = word.lower()
    if lower in _SUFFIX_CASING:
        return _SUFFIX_CASING[lower]
    m = _MC_RE.match(lower)
    if m and len(lower) > 2:
        return "Mc" + m.group(1).upper() + m.group(2)
    m = _MAC_RE.match(lower)
    if m and len(lower) > 3:
        return "Mac" + m.group(1).upper() + m.group(2)
    return lower[0].upper() + lower[1:]


def titlecase_name(value):
    """Title-case a name, splitting on (and preserving) spaces, hyphens,
    and apostrophes: "DI FILIPPO" -> "Di Filippo", "MCDERMOTT" ->
    "McDermott", "O'BRIEN" -> "O'Brien", "MORA III" -> "Mora III"."""
    if not value:
        return value
    parts = re.split(r"([\s\-'])", value.strip())
    return "".join(part if part in (" ", "-", "'") else _cap_word(part) for part in parts)
