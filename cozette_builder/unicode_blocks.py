import bisect
import re
import unicodedata
import urllib.request
from pathlib import Path

from fontTools.agl import LEGACY_AGL2UV, UV2AGL

UCD = f"https://www.unicode.org/Public/{unicodedata.unidata_version}/ucd/"


def ucd(filename):
    """Read a file from the Unicode database, yield the fields of each line."""
    with urllib.request.urlopen(UCD + filename) as f:
        for line in f.read().decode("utf-8").splitlines():
            line = line.split("#")[0].strip()
            if line:
                yield [field.strip() for field in line.split(";")]


# Blocks: "0000..007F; Basic Latin"
BLOCKS = []
for code_range, name in ucd("Blocks.txt"):
    start, end = (int(x, 16) for x in code_range.split(".."))
    BLOCKS.append((start, end, name))

STARTS = [b[0] for b in BLOCKS]

# Aliases: "0000;NUL;abbreviation" (we keep the first abbreviation)
ALIASES = {}
for codepoint, alias, kind in ucd("NameAliases.txt"):
    if kind == "abbreviation":
        ALIASES.setdefault(int(codepoint, 16), alias)

PLANES = {
    0: "Basic Multilingual Plane",
    1: "Supplementary Multilingual Plane",
    2: "Supplementary Ideographic Plane",
    3: "Tertiary Ideographic Plane",
    14: "Supplementary Special-purpose Plane",
    15: "Supplementary Private Use Area-A",
    16: "Supplementary Private Use Area-B",
}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def unicode_path(codepoint: int) -> Path:
    plane = codepoint >> 16
    plane_dir = f"{plane:02X}-{slug(PLANES.get(plane, 'unassigned'))}"

    i = bisect.bisect_right(STARTS, codepoint) - 1
    if i >= 0 and codepoint <= BLOCKS[i][1]:
        block_dir = f"{BLOCKS[i][0]:04X}-{slug(BLOCKS[i][2])}"
    else:
        block_dir = "no-block"

    name = unicodedata.name(chr(codepoint), None) or ALIASES.get(codepoint)
    filename = (
        f"{codepoint:04X}-{slug(name)}.txt" if name else f"{codepoint:04X}.txt"
    )

    return Path(plane_dir, block_dir, filename)


# Old Adobe names missing from AGLFN:
# keep only the "afii…" and "…commaaccent" ones
LEGACY_NAMES = {}
for _name, _codepoints in sorted(LEGACY_AGL2UV.items()):
    if len(_codepoints) == 1 and (
        _name.startswith("afii") or _name.endswith("commaaccent")
    ):
        LEGACY_NAMES.setdefault(_codepoints[0], _name)


def glyph_name(codepoint: int) -> str:
    """Return the BDF STARTCHAR name for a codepoint."""
    if codepoint in UV2AGL:
        return UV2AGL[codepoint]
    if codepoint in LEGACY_NAMES:
        return LEGACY_NAMES[codepoint]
    if codepoint <= 0xFFFF:
        return f"uni{codepoint:04X}"
    return f"u{codepoint:05X}"


def parse_unicode_path(path: str | Path) -> tuple[int, str]:
    """Return (codepoint, STARTCHAR name) from a glyph path."""
    stem = Path(path).stem  # "E0023-tag-number-sign"
    codepoint = int(stem.split("-", 1)[0], 16)  # 0xE0023

    return codepoint, glyph_name(codepoint)
