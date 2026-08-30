#
# 🬦🬋🬢🬦🬋🬏🬦🬋🬋    🬓       🬦🬋🬋 🬩🬃🬞🬋🬢 🬨     🬓                       🬓
# ▐🬋🬤▐ ▐▐🬋🬃   🬁🬕🬀🬦🬂🬧   ▐🬋🬃 ▐ ▐ 🬭 ▐ 🬦🬰🬶🬁🬕🬀   🬦🬂🬈🬦🬂🬧▐🬂🬧🬉🬏🬘🬦🬰🬶▐🬂🬈🬁🬕🬀🬦🬰🬶▐🬂🬈
# ▐🬭🬘▐🬭🬅▐      🬣🬭🬉🬭🬘   ▐   🬷🬏🬉🬭🬘 ▐🬏🬉🬭🬖 🬣🬭   🬉🬭🬖🬉🬭🬘▐ ▐ 🬧🬀🬉🬭🬖▐   🬣🬭🬉🬭🬖▐
# 
# This Python script is a BDF to FIGlet pseudo-pixels / mosaics converter
# 
# It parses a BDF file, grabbing some metadata and bitmaps, and passes the
# in-memory object built from the BDF though some processing to normalize
# their bitmaps to regular canvas tailored fo the specific pseudo-pixels type
# requested, optionally extending them if required to avoid cropping
# overhangs, adding a "missing character" (tofu) FIGlet replacement
# character, ... and then export the font to a FIGlet FLF2 file, converting
# the processed BDF bitmaps to the requested pseudo-pixels type: full-blocks,
# half-blocks, quadrants, sextants, octants, separated quadrants, separated
# sextants, or Braille.
# This gives us a fully-automated FIGlet companion font generator for bitmap
# fonts, making it possible to use the same glyphs for the terminal and the
# titles/banners rendered using FIGlet or compatible utilities.
# 
# Sorry to Python coders, you can probably tell it isn't my usual
# programming language and I probably hacked the language into performing a
# more C-like process, and I kept the structures as close to their original
# formats as possible, which explains the really weird bitmap format
# inherited from the BDF format.  Hopefully it is still understandable.
# 
# - Philippe Majerus, August 2026  -  Last updated on August 30, 2026
# 
# 
# ---------------------------------------------------------------------------
# MIT License
# 
# Copyright (c) 2026 Philippe Majerus (phm.lu)
# 
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE # SOFTWARE.
# ---------------------------------------------------------------------------


from enum import IntEnum  # We use this to provide names for the density arg.
import copy  # We need copy.deepcopy in build_flf2
import zipfile, os, tempfile, shutil   # We use these for zip_in_place
from datetime import datetime, timezone   # We use these for timestamping



############################################################################
#
# This first part is a Unicode pseudo-pixels / mosaics renderer.
# We take BDF bitmaps, representing monochromatic bitmaps, and convert them
# to a FIGlet character. It can use full-blocks, half-blocks, quadrants,
# sextants, octants, separated quadrants, separated sextants, or Braille.
# To avoid any risk of Python interferring with our Unicode markup, we use
# bytearrays containing explicit UTF-8 bytes sequences instead of strings.
# This avoids any risk of Python trying to be smart and fixing our Unicode
# 16.0 characters it doesn't know to something outdated it considers more
# valid.
# 
# The whole section provides a single function, bmp_to_figchar(bmp, height,
# width, pixels_per_character), where img is a BDF bitmap (a list of
# horizontal pixels stores as the bits of the numbers stored in the list)
# The height and width specifies the dimensions of the bitmap, and
# pixels_per_character can be 2, 4, 6, or 8 to specify the type of
# characters to use. The returned value is a byte buffer containing the
# FIGlet character, including the EOL markers, ready to be written to
# a .flf file.
#


# Full-blocks lookup table used by bmp_to_figchar
FULLBLOCK_MAP = (
	b"\xC2\xA0",          #   NO-BREAK SPACE
	b"\xE2\x96\x88"       # █ FULL BLOCK
)


# Half-blocks lookup table used by bmp_to_figchar
HALFBLOCK_MAP = (
	#
	# This maps a 1bpp 1x2 bitmap to a single half-block character as UTF‑8 bytes.
	#
	b"\xC2\xA0",          #   NO-BREAK SPACE
	b"\xE2\x96\x80",      # ▀ UPPER HALF BLOCK
	b"\xE2\x96\x84",      # ▄ LOWER HALF BLOCK
	b"\xE2\x96\x88"       # █ FULL BLOCK
)


# Quadrant lookup table used by bmp_to_figchar
QUADRANT_MAP  = (
	#
	# This maps a 1bpp 2x2 bitmap to a single quadrant character as UTF‑8 bytes.
	# Each quadrant is indexed by a 4‑bit value formed from the pixels of a 2x2
	# block.
	# The bit positions (1–4) correspond to the pixels arranged visually as:
	#
	#      +---+---+
	#      | 2 | 1 | LSB
	#      +---+---+
	#  MSB | 4 | 3 |
	#      +---+---+
	#
	# This is a very unusual bitmap bits arrangement, but is the one used
	# by BDF, so this makes the lookup during conversion more efficient.
	#
	b"\xC2\xA0",          #   NO-BREAK SPACE
	b"\xE2\x96\x9D",      # ▝ QUADRANT UPPER RIGHT
	b"\xE2\x96\x98",      # ▘ QUADRANT UPPER LEFT
	b"\xE2\x96\x80",      # ▀ UPPER HALF BLOCK
	b"\xE2\x96\x97",      # ▗ QUADRANT LOWER RIGHT
	b"\xE2\x96\x90",      # ▐ RIGHT HALF BLOCK
	b"\xE2\x96\x9A",      # ▚ QUADRANT UPPER LEFT AND LOWER RIGHT
	b"\xE2\x96\x9C",      # ▜ QUADRANT UPPER LEFT AND UPPER RIGHT AND LOWER RIGHT
	b"\xE2\x96\x96",      # ▖ QUADRANT LOWER LEFT
	b"\xE2\x96\x9E",      # ▞ QUADRANT UPPER RIGHT AND LOWER LEFT
	b"\xE2\x96\x8C",      # ▌ LEFT HALF BLOCK
	b"\xE2\x96\x9B",      # ▛ QUADRANT UPPER LEFT AND UPPER RIGHT AND LOWER LEFT
	b"\xE2\x96\x84",      # ▄ LOWER HALF BLOCK
	b"\xE2\x96\x9F",      # ▟ QUADRANT UPPER RIGHT AND LOWER LEFT AND LOWER RIGHT
	b"\xE2\x96\x99",      # ▙ QUADRANT UPPER LEFT AND LOWER LEFT AND LOWER RIGHT
	b"\xE2\x96\x88"       # █ FULL BLOCK
)

# Same as above, but using the "separated" variants
SEPARATED_QUADRANT_MAP = (
    b"\xC2\xA0",          #   NO-BREAK SPACE
    b"\xF0\x9C\xB0\xA2",  # 𜰢 SEPARATED BLOCK QUADRANT-2
    b"\xF0\x9C\xB0\xA1",  # 𜰡 SEPARATED BLOCK QUADRANT-1
    b"\xF0\x9C\xB0\xA3",  # 𜰣 SEPARATED BLOCK QUADRANT-12
    b"\xF0\x9C\xB0\xA8",  # 𜰨 SEPARATED BLOCK QUADRANT-4
    b"\xF0\x9C\xB0\xAA",  # 𜰪 SEPARATED BLOCK QUADRANT-24
    b"\xF0\x9C\xB0\xA9",  # 𜰩 SEPARATED BLOCK QUADRANT-14
    b"\xF0\x9C\xB0\xAB",  # 𜰫 SEPARATED BLOCK QUADRANT-124
    b"\xF0\x9C\xB0\xA4",  # 𜰤 SEPARATED BLOCK QUADRANT-3
    b"\xF0\x9C\xB0\xA6",  # 𜰦 SEPARATED BLOCK QUADRANT-23
    b"\xF0\x9C\xB0\xA5",  # 𜰥 SEPARATED BLOCK QUADRANT-13
    b"\xF0\x9C\xB0\xA7",  # 𜰧 SEPARATED BLOCK QUADRANT-123
    b"\xF0\x9C\xB0\xAC",  # 𜰬 SEPARATED BLOCK QUADRANT-34
    b"\xF0\x9C\xB0\xAE",  # 𜰮 SEPARATED BLOCK QUADRANT-234
    b"\xF0\x9C\xB0\xAD",  # 𜰭 SEPARATED BLOCK QUADRANT-134
    b"\xF0\x9C\xB0\xAF"   # 𜰯 SEPARATED BLOCK QUADRANT-1234
)

# Sextants lookup table used by bmp_to_figchar
SEXTANT_MAP = (
	#
	# This maps a 1bpp 2x3 bitmap to a single sextant character as UTF‑8 bytes.
	# Each sextant is indexed by a 6‑bit value formed from the pixels of a 2x3
	# block.
	# The bit positions (1–6) correspond to the pixels arranged visually as:
	#
	#      +---+---+
	#      | 2 | 1 | LSB
	#      +---+---+
	#      | 4 | 3 |
	#      +---+---+
	#  MSB | 6 | 5 |
	#      +---+---+
	#
	# This is a very unusual bitmap bits arrangement, but is the one used
	# by BDF, so this makes the lookup during conversion more efficient.
	#
	b"\xC2\xA0",          #   NO-BREAK SPACE
	b"\xF0\x9F\xAC\x81",  # 🬁 BLOCK SEXTANT-2
	b"\xF0\x9F\xAC\x80",  # 🬀 BLOCK SEXTANT-1
	b"\xF0\x9F\xAC\x82",  # 🬂 BLOCK SEXTANT-12
	b"\xF0\x9F\xAC\x87",  # 🬇 BLOCK SEXTANT-4
	b"\xF0\x9F\xAC\x89",  # 🬉 BLOCK SEXTANT-24
	b"\xF0\x9F\xAC\x88",  # 🬈 BLOCK SEXTANT-14
	b"\xF0\x9F\xAC\x8A",  # 🬊 BLOCK SEXTANT-124
	b"\xF0\x9F\xAC\x83",  # 🬃 BLOCK SEXTANT-3
	b"\xF0\x9F\xAC\x85",  # 🬅 BLOCK SEXTANT-23
	b"\xF0\x9F\xAC\x84",  # 🬄 BLOCK SEXTANT-13
	b"\xF0\x9F\xAC\x86",  # 🬆 BLOCK SEXTANT-123
	b"\xF0\x9F\xAC\x8B",  # 🬋 BLOCK SEXTANT-34
	b"\xF0\x9F\xAC\x8D",  # 🬍 BLOCK SEXTANT-234
	b"\xF0\x9F\xAC\x8C",  # 🬌 BLOCK SEXTANT-134
	b"\xF0\x9F\xAC\x8E",  # 🬎 BLOCK SEXTANT-1234
	b"\xF0\x9F\xAC\x9E",  # 🬞 BLOCK SEXTANT-6
	b"\xF0\x9F\xAC\xA0",  # 🬠 BLOCK SEXTANT-26
	b"\xF0\x9F\xAC\x9F",  # 🬟 BLOCK SEXTANT-16
	b"\xF0\x9F\xAC\xA1",  # 🬡 BLOCK SEXTANT-126
	b"\xF0\x9F\xAC\xA6",  # 🬦 BLOCK SEXTANT-46
	b"\xE2\x96\x90",      # ▐ RIGHT HALF BLOCK
	b"\xF0\x9F\xAC\xA7",  # 🬧 BLOCK SEXTANT-146
	b"\xF0\x9F\xAC\xA8",  # 🬨 BLOCK SEXTANT-1246
	b"\xF0\x9F\xAC\xA2",  # 🬢 BLOCK SEXTANT-36
	b"\xF0\x9F\xAC\xA4",  # 🬤 BLOCK SEXTANT-236
	b"\xF0\x9F\xAC\xA3",  # 🬣 BLOCK SEXTANT-136
	b"\xF0\x9F\xAC\xA5",  # 🬥 BLOCK SEXTANT-1236
	b"\xF0\x9F\xAC\xA9",  # 🬩 BLOCK SEXTANT-346
	b"\xF0\x9F\xAC\xAB",  # 🬫 BLOCK SEXTANT-2346
	b"\xF0\x9F\xAC\xAA",  # 🬪 BLOCK SEXTANT-1346
	b"\xF0\x9F\xAC\xAC",  # 🬬 BLOCK SEXTANT-12346
	b"\xF0\x9F\xAC\x8F",  # 🬏 BLOCK SEXTANT-5
	b"\xF0\x9F\xAC\x91",  # 🬑 BLOCK SEXTANT-25
	b"\xF0\x9F\xAC\x90",  # 🬐 BLOCK SEXTANT-15
	b"\xF0\x9F\xAC\x92",  # 🬒 BLOCK SEXTANT-125
	b"\xF0\x9F\xAC\x96",  # 🬖 BLOCK SEXTANT-45
	b"\xF0\x9F\xAC\x98",  # 🬘 BLOCK SEXTANT-245
	b"\xF0\x9F\xAC\x97",  # 🬗 BLOCK SEXTANT-145
	b"\xF0\x9F\xAC\x99",  # 🬙 BLOCK SEXTANT-1245
	b"\xF0\x9F\xAC\x93",  # 🬓 BLOCK SEXTANT-35
	b"\xF0\x9F\xAC\x94",  # 🬔 BLOCK SEXTANT-235
	b"\xE2\x96\x8C",      # ▌ LEFT HALF BLOCK
	b"\xF0\x9F\xAC\x95",  # 🬕 BLOCK SEXTANT-1235
	b"\xF0\x9F\xAC\x9A",  # 🬚 BLOCK SEXTANT-345
	b"\xF0\x9F\xAC\x9C",  # 🬜 BLOCK SEXTANT-2345
	b"\xF0\x9F\xAC\x9B",  # 🬛 BLOCK SEXTANT-1345
	b"\xF0\x9F\xAC\x9D",  # 🬝 BLOCK SEXTANT-12345
	b"\xF0\x9F\xAC\xAD",  # 🬭 BLOCK SEXTANT-56
	b"\xF0\x9F\xAC\xAF",  # 🬯 BLOCK SEXTANT-256
	b"\xF0\x9F\xAC\xAE",  # 🬮 BLOCK SEXTANT-156
	b"\xF0\x9F\xAC\xB0",  # 🬰 BLOCK SEXTANT-1256
	b"\xF0\x9F\xAC\xB5",  # 🬵 BLOCK SEXTANT-456
	b"\xF0\x9F\xAC\xB7",  # 🬷 BLOCK SEXTANT-2456
	b"\xF0\x9F\xAC\xB6",  # 🬶 BLOCK SEXTANT-1456
	b"\xF0\x9F\xAC\xB8",  # 🬸 BLOCK SEXTANT-12456
	b"\xF0\x9F\xAC\xB1",  # 🬱 BLOCK SEXTANT-356
	b"\xF0\x9F\xAC\xB3",  # 🬳 BLOCK SEXTANT-2356
	b"\xF0\x9F\xAC\xB2",  # 🬲 BLOCK SEXTANT-1356
	b"\xF0\x9F\xAC\xB4",  # 🬴 BLOCK SEXTANT-12356
	b"\xF0\x9F\xAC\xB9",  # 🬹 BLOCK SEXTANT-3456
	b"\xF0\x9F\xAC\xBB",  # 🬻 BLOCK SEXTANT-23456
	b"\xF0\x9F\xAC\xBA",  # 🬺 BLOCK SEXTANT-13456
	b"\xE2\x96\x88"       # █ FULL BLOCK
)

# Same as above, but using the "separated" variants
SEPARATED_SEXTANT_MAP = (
    b"\xC2\xA0",          #   NO-BREAK SPACE
    b"\xF0\x9C\xB9\x92",  # 𜹒 SEPARATED BLOCK SEXTANT-2
    b"\xF0\x9C\xB9\x91",  # 𜹑 SEPARATED BLOCK SEXTANT-1
    b"\xF0\x9C\xB9\x93",  # 𜹓 SEPARATED BLOCK SEXTANT-12
    b"\xF0\x9C\xB9\x98",  # 𜹘 SEPARATED BLOCK SEXTANT-4
    b"\xF0\x9C\xB9\x9A",  # 𜹚 SEPARATED BLOCK SEXTANT-24
    b"\xF0\x9C\xB9\x99",  # 𜹙 SEPARATED BLOCK SEXTANT-14
    b"\xF0\x9C\xB9\x9B",  # 𜹛 SEPARATED BLOCK SEXTANT-124
    b"\xF0\x9C\xB9\x94",  # 𜹔 SEPARATED BLOCK SEXTANT-3
    b"\xF0\x9C\xB9\x96",  # 𜹖 SEPARATED BLOCK SEXTANT-23
    b"\xF0\x9C\xB9\x95",  # 𜹕 SEPARATED BLOCK SEXTANT-13
    b"\xF0\x9C\xB9\x97",  # 𜹗 SEPARATED BLOCK SEXTANT-123
    b"\xF0\x9C\xB9\x9C",  # 𜹜 SEPARATED BLOCK SEXTANT-34
    b"\xF0\x9C\xB9\x9E",  # 𜹞 SEPARATED BLOCK SEXTANT-234
    b"\xF0\x9C\xB9\x9D",  # 𜹝 SEPARATED BLOCK SEXTANT-134
    b"\xF0\x9C\xB9\x9F",  # 𜹟 SEPARATED BLOCK SEXTANT-1234
    b"\xF0\x9C\xB9\xB0",  # 𜹰 SEPARATED BLOCK SEXTANT-6
    b"\xF0\x9C\xB9\xB2",  # 𜹲 SEPARATED BLOCK SEXTANT-26
    b"\xF0\x9C\xB9\xB1",  # 𜹱 SEPARATED BLOCK SEXTANT-16
    b"\xF0\x9C\xB9\xB3",  # 𜹳 SEPARATED BLOCK SEXTANT-126
    b"\xF0\x9C\xB9\xB8",  # 𜹸 SEPARATED BLOCK SEXTANT-46
    b"\xF0\x9C\xB9\xBA",  # 𜹺 SEPARATED BLOCK SEXTANT-246
    b"\xF0\x9C\xB9\xB9",  # 𜹹 SEPARATED BLOCK SEXTANT-146
    b"\xF0\x9C\xB9\xBB",  # 𜹻 SEPARATED BLOCK SEXTANT-1246
    b"\xF0\x9C\xB9\xB4",  # 𜹴 SEPARATED BLOCK SEXTANT-36
    b"\xF0\x9C\xB9\xB6",  # 𜹶 SEPARATED BLOCK SEXTANT-236
    b"\xF0\x9C\xB9\xB5",  # 𜹵 SEPARATED BLOCK SEXTANT-136
    b"\xF0\x9C\xB9\xB7",  # 𜹷 SEPARATED BLOCK SEXTANT-1236
    b"\xF0\x9C\xB9\xBC",  # 𜹼 SEPARATED BLOCK SEXTANT-346
    b"\xF0\x9C\xB9\xBE",  # 𜹾 SEPARATED BLOCK SEXTANT-2346
    b"\xF0\x9C\xB9\xBD",  # 𜹽 SEPARATED BLOCK SEXTANT-1346
    b"\xF0\x9C\xB9\xBF",  # 𜹿 SEPARATED BLOCK SEXTANT-12346
    b"\xF0\x9C\xB9\xA0",  # 𜹠 SEPARATED BLOCK SEXTANT-5
    b"\xF0\x9C\xB9\xA2",  # 𜹢 SEPARATED BLOCK SEXTANT-25
    b"\xF0\x9C\xB9\xA1",  # 𜹡 SEPARATED BLOCK SEXTANT-15
    b"\xF0\x9C\xB9\xA3",  # 𜹣 SEPARATED BLOCK SEXTANT-125
    b"\xF0\x9C\xB9\xA8",  # 𜹨 SEPARATED BLOCK SEXTANT-45
    b"\xF0\x9C\xB9\xAA",  # 𜹪 SEPARATED BLOCK SEXTANT-245
    b"\xF0\x9C\xB9\xA9",  # 𜹩 SEPARATED BLOCK SEXTANT-145
    b"\xF0\x9C\xB9\xAB",  # 𜹫 SEPARATED BLOCK SEXTANT-1245
    b"\xF0\x9C\xB9\xA4",  # 𜹤 SEPARATED BLOCK SEXTANT-35
    b"\xF0\x9C\xB9\xA6",  # 𜹦 SEPARATED BLOCK SEXTANT-235
    b"\xF0\x9C\xB9\xA5",  # 𜹥 SEPARATED BLOCK SEXTANT-135
    b"\xF0\x9C\xB9\xA7",  # 𜹧 SEPARATED BLOCK SEXTANT-1235
    b"\xF0\x9C\xB9\xAC",  # 𜹬 SEPARATED BLOCK SEXTANT-345
    b"\xF0\x9C\xB9\xAE",  # 𜹮 SEPARATED BLOCK SEXTANT-2345
    b"\xF0\x9C\xB9\xAD",  # 𜹭 SEPARATED BLOCK SEXTANT-1345
    b"\xF0\x9C\xB9\xAF",  # 𜹯 SEPARATED BLOCK SEXTANT-12345
    b"\xF0\x9C\xBA\x80",  # 𜺀 SEPARATED BLOCK SEXTANT-56
    b"\xF0\x9C\xBA\x82",  # 𜺂 SEPARATED BLOCK SEXTANT-256
    b"\xF0\x9C\xBA\x81",  # 𜺁 SEPARATED BLOCK SEXTANT-156
    b"\xF0\x9C\xBA\x83",  # 𜺃 SEPARATED BLOCK SEXTANT-1256
    b"\xF0\x9C\xBA\x88",  # 𜺈 SEPARATED BLOCK SEXTANT-456
    b"\xF0\x9C\xBA\x8A",  # 𜺊 SEPARATED BLOCK SEXTANT-2456
    b"\xF0\x9C\xBA\x89",  # 𜺉 SEPARATED BLOCK SEXTANT-1456
    b"\xF0\x9C\xBA\x8B",  # 𜺋 SEPARATED BLOCK SEXTANT-12456
    b"\xF0\x9C\xBA\x84",  # 𜺄 SEPARATED BLOCK SEXTANT-356
    b"\xF0\x9C\xBA\x86",  # 𜺆 SEPARATED BLOCK SEXTANT-2356
    b"\xF0\x9C\xBA\x85",  # 𜺅 SEPARATED BLOCK SEXTANT-1356
    b"\xF0\x9C\xBA\x87",  # 𜺇 SEPARATED BLOCK SEXTANT-12356
    b"\xF0\x9C\xBA\x8C",  # 𜺌 SEPARATED BLOCK SEXTANT-3456
    b"\xF0\x9C\xBA\x8E",  # 𜺎 SEPARATED BLOCK SEXTANT-23456
    b"\xF0\x9C\xBA\x8D",  # 𜺍 SEPARATED BLOCK SEXTANT-13456
    b"\xF0\x9C\xBA\x8F"   # 𜺏 SEPARATED BLOCK SEXTANT-123456
)

# Octants lookup table used by bmp_to_figchar
OCTANT_MAP = (
	#
	# This maps a 1bpp 2x4 bitmap to a single octant character as UTF‑8 bytes.
	# Each octant is indexed by an 8‑bit value formed from the pixels of a 2x4
	# block.
	# The bit positions (1–8) correspond to the pixels arranged visually as:
	#
	#      +---+---+
	#      | 2 | 1 | LSB
	#      +---+---+
	#      | 4 | 3 |
	#      +---+---+
	#      | 6 | 5 |
	#      +---+---+
	#  MSB | 8 | 7 |
	#      +---+---+
	#
	# This is a very unusual bitmap bits arrangement, but is the one used
	# by BDF, so this makes the lookup during conversion more efficient.
	#
	b"\xC2\xA0",          #   NO-BREAK SPACE
	b"\xF0\x9C\xBA\xAB",  # 𜺫 RIGHT HALF UPPER ONE QUARTER BLOCK
	b"\xF0\x9C\xBA\xA8",  # 𜺨 LEFT HALF UPPER ONE QUARTER BLOCK
	b"\xF0\x9F\xAE\x82",  # 🮂 UPPER ONE QUARTER BLOCK
	b"\xF0\x9C\xB4\x83",  # 𜴃 BLOCK OCTANT-4
	b"\xE2\x96\x9D",      # ▝ QUADRANT UPPER RIGHT
	b"\xF0\x9C\xB4\x84",  # 𜴄 BLOCK OCTANT-14
	b"\xF0\x9C\xB4\x85",  # 𜴅 BLOCK OCTANT-124
	b"\xF0\x9C\xB4\x80",  # 𜴀 BLOCK OCTANT-3
	b"\xF0\x9C\xB4\x81",  # 𜴁 BLOCK OCTANT-23
	b"\xE2\x96\x98",      # ▘ QUADRANT UPPER LEFT
	b"\xF0\x9C\xB4\x82",  # 𜴂 BLOCK OCTANT-123
	b"\xF0\x9C\xB4\x86",  # 𜴆 BLOCK OCTANT-34
	b"\xF0\x9C\xB4\x88",  # 𜴈 BLOCK OCTANT-234
	b"\xF0\x9C\xB4\x87",  # 𜴇 BLOCK OCTANT-134
	b"\xE2\x96\x80",      # ▀ UPPER HALF BLOCK
	b"\xF0\x9C\xB4\x98",  # 𜴘 BLOCK OCTANT-6
	b"\xF0\x9C\xB4\x9A",  # 𜴚 BLOCK OCTANT-26
	b"\xF0\x9C\xB4\x99",  # 𜴙 BLOCK OCTANT-16
	b"\xF0\x9C\xB4\x9B",  # 𜴛 BLOCK OCTANT-126
	b"\xF0\x9F\xAF\xA7",  # 🯧 MIDDLE RIGHT ONE QUARTER BLOCK
	b"\xF0\x9C\xB4\xA1",  # 𜴡 BLOCK OCTANT-246
	b"\xF0\x9C\xB4\xA0",  # 𜴠 BLOCK OCTANT-146
	b"\xF0\x9C\xB4\xA2",  # 𜴢 BLOCK OCTANT-1246
	b"\xF0\x9C\xB4\x9C",  # 𜴜 BLOCK OCTANT-36
	b"\xF0\x9C\xB4\x9E",  # 𜴞 BLOCK OCTANT-236
	b"\xF0\x9C\xB4\x9D",  # 𜴝 BLOCK OCTANT-136
	b"\xF0\x9C\xB4\x9F",  # 𜴟 BLOCK OCTANT-1236
	b"\xF0\x9C\xB4\xA3",  # 𜴣 BLOCK OCTANT-346
	b"\xF0\x9C\xB4\xA5",  # 𜴥 BLOCK OCTANT-2346
	b"\xF0\x9C\xB4\xA4",  # 𜴤 BLOCK OCTANT-1346
	b"\xF0\x9C\xB4\xA6",  # 𜴦 BLOCK OCTANT-12346
	b"\xF0\x9C\xB4\x89",  # 𜴉 BLOCK OCTANT-5
	b"\xF0\x9C\xB4\x8B",  # 𜴋 BLOCK OCTANT-25
	b"\xF0\x9C\xB4\x8A",  # 𜴊 BLOCK OCTANT-15
	b"\xF0\x9C\xB4\x8C",  # 𜴌 BLOCK OCTANT-125
	b"\xF0\x9C\xB4\x90",  # 𜴐 BLOCK OCTANT-45
	b"\xF0\x9C\xB4\x92",  # 𜴒 BLOCK OCTANT-245
	b"\xF0\x9C\xB4\x91",  # 𜴑 BLOCK OCTANT-145
	b"\xF0\x9C\xB4\x93",  # 𜴓 BLOCK OCTANT-1245
	b"\xF0\x9F\xAF\xA6",  # 🯦 MIDDLE LEFT ONE QUARTER BLOCK
	b"\xF0\x9C\xB4\x8E",  # 𜴎 BLOCK OCTANT-235
	b"\xF0\x9C\xB4\x8D",  # 𜴍 BLOCK OCTANT-135
	b"\xF0\x9C\xB4\x8F",  # 𜴏 BLOCK OCTANT-1235
	b"\xF0\x9C\xB4\x94",  # 𜴔 BLOCK OCTANT-345
	b"\xF0\x9C\xB4\x96",  # 𜴖 BLOCK OCTANT-2345
	b"\xF0\x9C\xB4\x95",  # 𜴕 BLOCK OCTANT-1345
	b"\xF0\x9C\xB4\x97",  # 𜴗 BLOCK OCTANT-12345
	b"\xF0\x9C\xB4\xA7",  # 𜴧 BLOCK OCTANT-56
	b"\xF0\x9C\xB4\xA9",  # 𜴩 BLOCK OCTANT-256
	b"\xF0\x9C\xB4\xA8",  # 𜴨 BLOCK OCTANT-156
	b"\xF0\x9C\xB4\xAA",  # 𜴪 BLOCK OCTANT-1256
	b"\xF0\x9C\xB4\xAF",  # 𜴯 BLOCK OCTANT-456
	b"\xF0\x9C\xB4\xB1",  # 𜴱 BLOCK OCTANT-2456
	b"\xF0\x9C\xB4\xB0",  # 𜴰 BLOCK OCTANT-1456
	b"\xF0\x9C\xB4\xB2",  # 𜴲 BLOCK OCTANT-12456
	b"\xF0\x9C\xB4\xAB",  # 𜴫 BLOCK OCTANT-356
	b"\xF0\x9C\xB4\xAD",  # 𜴭 BLOCK OCTANT-2356
	b"\xF0\x9C\xB4\xAC",  # 𜴬 BLOCK OCTANT-1356
	b"\xF0\x9C\xB4\xAE",  # 𜴮 BLOCK OCTANT-12356
	b"\xF0\x9C\xB4\xB3",  # 𜴳 BLOCK OCTANT-3456
	b"\xF0\x9C\xB4\xB5",  # 𜴵 BLOCK OCTANT-23456
	b"\xF0\x9C\xB4\xB4",  # 𜴴 BLOCK OCTANT-13456
	b"\xF0\x9F\xAE\x85",  # 🮅 UPPER THREE QUARTERS BLOCK
	b"\xF0\x9C\xBA\xA0",  # 𜺠 RIGHT HALF LOWER ONE QUARTER BLOCK
	b"\xF0\x9C\xB5\xB2",  # 𜵲 BLOCK OCTANT-28
	b"\xF0\x9C\xB5\xB1",  # 𜵱 BLOCK OCTANT-18
	b"\xF0\x9C\xB5\xB3",  # 𜵳 BLOCK OCTANT-128
	b"\xF0\x9C\xB5\xB8",  # 𜵸 BLOCK OCTANT-48
	b"\xF0\x9C\xB5\xBA",  # 𜵺 BLOCK OCTANT-248
	b"\xF0\x9C\xB5\xB9",  # 𜵹 BLOCK OCTANT-148
	b"\xF0\x9C\xB5\xBB",  # 𜵻 BLOCK OCTANT-1248
	b"\xF0\x9C\xB5\xB4",  # 𜵴 BLOCK OCTANT-38
	b"\xF0\x9C\xB5\xB6",  # 𜵶 BLOCK OCTANT-238
	b"\xF0\x9C\xB5\xB5",  # 𜵵 BLOCK OCTANT-138
	b"\xF0\x9C\xB5\xB7",  # 𜵷 BLOCK OCTANT-1238
	b"\xF0\x9C\xB5\xBC",  # 𜵼 BLOCK OCTANT-348
	b"\xF0\x9C\xB5\xBE",  # 𜵾 BLOCK OCTANT-2348
	b"\xF0\x9C\xB5\xBD",  # 𜵽 BLOCK OCTANT-1348
	b"\xF0\x9C\xB5\xBF",  # 𜵿 BLOCK OCTANT-12348
	b"\xE2\x96\x97",      # ▗ QUADRANT LOWER RIGHT
	b"\xF0\x9C\xB6\x91",  # 𜶑 BLOCK OCTANT-268
	b"\xF0\x9C\xB6\x90",  # 𜶐 BLOCK OCTANT-168
	b"\xF0\x9C\xB6\x92",  # 𜶒 BLOCK OCTANT-1268
	b"\xF0\x9C\xB6\x96",  # 𜶖 BLOCK OCTANT-468
	b"\xE2\x96\x90",      # ▐ RIGHT HALF BLOCK
	b"\xF0\x9C\xB6\x97",  # 𜶗 BLOCK OCTANT-1468
	b"\xF0\x9C\xB6\x98",  # 𜶘 BLOCK OCTANT-12468
	b"\xF0\x9C\xB6\x93",  # 𜶓 BLOCK OCTANT-368
	b"\xF0\x9C\xB6\x94",  # 𜶔 BLOCK OCTANT-2368
	b"\xE2\x96\x9A",      # ▚ QUADRANT UPPER LEFT AND LOWER RIGHT
	b"\xF0\x9C\xB6\x95",  # 𜶕 BLOCK OCTANT-12368
	b"\xF0\x9C\xB6\x99",  # 𜶙 BLOCK OCTANT-3468
	b"\xF0\x9C\xB6\x9B",  # 𜶛 BLOCK OCTANT-23468
	b"\xF0\x9C\xB6\x9A",  # 𜶚 BLOCK OCTANT-13468
	b"\xE2\x96\x9C",      # ▜ QUADRANT UPPER LEFT AND UPPER RIGHT AND LOWER RIGHT
	b"\xF0\x9C\xB6\x80",  # 𜶀 BLOCK OCTANT-58
	b"\xF0\x9C\xB6\x82",  # 𜶂 BLOCK OCTANT-258
	b"\xF0\x9C\xB6\x81",  # 𜶁 BLOCK OCTANT-158
	b"\xF0\x9C\xB6\x83",  # 𜶃 BLOCK OCTANT-1258
	b"\xF0\x9C\xB6\x88",  # 𜶈 BLOCK OCTANT-458
	b"\xF0\x9C\xB6\x8A",  # 𜶊 BLOCK OCTANT-2458
	b"\xF0\x9C\xB6\x89",  # 𜶉 BLOCK OCTANT-1458
	b"\xF0\x9C\xB6\x8B",  # 𜶋 BLOCK OCTANT-12458
	b"\xF0\x9C\xB6\x84",  # 𜶄 BLOCK OCTANT-358
	b"\xF0\x9C\xB6\x86",  # 𜶆 BLOCK OCTANT-2358
	b"\xF0\x9C\xB6\x85",  # 𜶅 BLOCK OCTANT-1358
	b"\xF0\x9C\xB6\x87",  # 𜶇 BLOCK OCTANT-12358
	b"\xF0\x9C\xB6\x8C",  # 𜶌 BLOCK OCTANT-3458
	b"\xF0\x9C\xB6\x8E",  # 𜶎 BLOCK OCTANT-23458
	b"\xF0\x9C\xB6\x8D",  # 𜶍 BLOCK OCTANT-13458
	b"\xF0\x9C\xB6\x8F",  # 𜶏 BLOCK OCTANT-123458
	b"\xF0\x9C\xB6\x9C",  # 𜶜 BLOCK OCTANT-568
	b"\xF0\x9C\xB6\x9E",  # 𜶞 BLOCK OCTANT-2568
	b"\xF0\x9C\xB6\x9D",  # 𜶝 BLOCK OCTANT-1568
	b"\xF0\x9C\xB6\x9F",  # 𜶟 BLOCK OCTANT-12568
	b"\xF0\x9C\xB6\xA4",  # 𜶤 BLOCK OCTANT-4568
	b"\xF0\x9C\xB6\xA6",  # 𜶦 BLOCK OCTANT-24568
	b"\xF0\x9C\xB6\xA5",  # 𜶥 BLOCK OCTANT-14568
	b"\xF0\x9C\xB6\xA7",  # 𜶧 BLOCK OCTANT-124568
	b"\xF0\x9C\xB6\xA0",  # 𜶠 BLOCK OCTANT-3568
	b"\xF0\x9C\xB6\xA2",  # 𜶢 BLOCK OCTANT-23568
	b"\xF0\x9C\xB6\xA1",  # 𜶡 BLOCK OCTANT-13568
	b"\xF0\x9C\xB6\xA3",  # 𜶣 BLOCK OCTANT-123568
	b"\xF0\x9C\xB6\xA8",  # 𜶨 BLOCK OCTANT-34568
	b"\xF0\x9C\xB6\xAA",  # 𜶪 BLOCK OCTANT-234568
	b"\xF0\x9C\xB6\xA9",  # 𜶩 BLOCK OCTANT-134568
	b"\xF0\x9C\xB6\xAB",  # 𜶫 BLOCK OCTANT-1234568
	b"\xF0\x9C\xBA\xA3",  # 𜺣 LEFT HALF LOWER ONE QUARTER BLOCK
	b"\xF0\x9C\xB4\xB7",  # 𜴷 BLOCK OCTANT-27
	b"\xF0\x9C\xB4\xB6",  # 𜴶 BLOCK OCTANT-17
	b"\xF0\x9C\xB4\xB8",  # 𜴸 BLOCK OCTANT-127
	b"\xF0\x9C\xB4\xBD",  # 𜴽 BLOCK OCTANT-47
	b"\xF0\x9C\xB4\xBF",  # 𜴿 BLOCK OCTANT-247
	b"\xF0\x9C\xB4\xBE",  # 𜴾 BLOCK OCTANT-147
	b"\xF0\x9C\xB5\x80",  # 𜵀 BLOCK OCTANT-1247
	b"\xF0\x9C\xB4\xB9",  # 𜴹 BLOCK OCTANT-37
	b"\xF0\x9C\xB4\xBB",  # 𜴻 BLOCK OCTANT-237
	b"\xF0\x9C\xB4\xBA",  # 𜴺 BLOCK OCTANT-137
	b"\xF0\x9C\xB4\xBC",  # 𜴼 BLOCK OCTANT-1237
	b"\xF0\x9C\xB5\x81",  # 𜵁 BLOCK OCTANT-347
	b"\xF0\x9C\xB5\x83",  # 𜵃 BLOCK OCTANT-2347
	b"\xF0\x9C\xB5\x82",  # 𜵂 BLOCK OCTANT-1347
	b"\xF0\x9C\xB5\x84",  # 𜵄 BLOCK OCTANT-12347
	b"\xF0\x9C\xB5\x91",  # 𜵑 BLOCK OCTANT-67
	b"\xF0\x9C\xB5\x93",  # 𜵓 BLOCK OCTANT-267
	b"\xF0\x9C\xB5\x92",  # 𜵒 BLOCK OCTANT-167
	b"\xF0\x9C\xB5\x94",  # 𜵔 BLOCK OCTANT-1267
	b"\xF0\x9C\xB5\x99",  # 𜵙 BLOCK OCTANT-467
	b"\xF0\x9C\xB5\x9B",  # 𜵛 BLOCK OCTANT-2467
	b"\xF0\x9C\xB5\x9A",  # 𜵚 BLOCK OCTANT-1467
	b"\xF0\x9C\xB5\x9C",  # 𜵜 BLOCK OCTANT-12467
	b"\xF0\x9C\xB5\x95",  # 𜵕 BLOCK OCTANT-367
	b"\xF0\x9C\xB5\x97",  # 𜵗 BLOCK OCTANT-2367
	b"\xF0\x9C\xB5\x96",  # 𜵖 BLOCK OCTANT-1367
	b"\xF0\x9C\xB5\x98",  # 𜵘 BLOCK OCTANT-12367
	b"\xF0\x9C\xB5\x9D",  # 𜵝 BLOCK OCTANT-3467
	b"\xF0\x9C\xB5\x9F",  # 𜵟 BLOCK OCTANT-23467
	b"\xF0\x9C\xB5\x9E",  # 𜵞 BLOCK OCTANT-13467
	b"\xF0\x9C\xB5\xA0",  # 𜵠 BLOCK OCTANT-123467
	b"\xE2\x96\x96",      # ▖ QUADRANT LOWER LEFT
	b"\xF0\x9C\xB5\x86",  # 𜵆 BLOCK OCTANT-257
	b"\xF0\x9C\xB5\x85",  # 𜵅 BLOCK OCTANT-157
	b"\xF0\x9C\xB5\x87",  # 𜵇 BLOCK OCTANT-1257
	b"\xF0\x9C\xB5\x8B",  # 𜵋 BLOCK OCTANT-457
	b"\xE2\x96\x9E",      # ▞ QUADRANT UPPER RIGHT AND LOWER LEFT
	b"\xF0\x9C\xB5\x8C",  # 𜵌 BLOCK OCTANT-1457
	b"\xF0\x9C\xB5\x8D",  # 𜵍 BLOCK OCTANT-12457
	b"\xF0\x9C\xB5\x88",  # 𜵈 BLOCK OCTANT-357
	b"\xF0\x9C\xB5\x89",  # 𜵉 BLOCK OCTANT-2357
	b"\xE2\x96\x8C",      # ▌ LEFT HALF BLOCK
	b"\xF0\x9C\xB5\x8A",  # 𜵊 BLOCK OCTANT-12357
	b"\xF0\x9C\xB5\x8E",  # 𜵎 BLOCK OCTANT-3457
	b"\xF0\x9C\xB5\x90",  # 𜵐 BLOCK OCTANT-23457
	b"\xF0\x9C\xB5\x8F",  # 𜵏 BLOCK OCTANT-13457
	b"\xE2\x96\x9B",      # ▛ QUADRANT UPPER LEFT AND UPPER RIGHT AND LOWER LEFT
	b"\xF0\x9C\xB5\xA1",  # 𜵡 BLOCK OCTANT-567
	b"\xF0\x9C\xB5\xA3",  # 𜵣 BLOCK OCTANT-2567
	b"\xF0\x9C\xB5\xA2",  # 𜵢 BLOCK OCTANT-1567
	b"\xF0\x9C\xB5\xA4",  # 𜵤 BLOCK OCTANT-12567
	b"\xF0\x9C\xB5\xA9",  # 𜵩 BLOCK OCTANT-4567
	b"\xF0\x9C\xB5\xAB",  # 𜵫 BLOCK OCTANT-24567
	b"\xF0\x9C\xB5\xAA",  # 𜵪 BLOCK OCTANT-14567
	b"\xF0\x9C\xB5\xAC",  # 𜵬 BLOCK OCTANT-124567
	b"\xF0\x9C\xB5\xA5",  # 𜵥 BLOCK OCTANT-3567
	b"\xF0\x9C\xB5\xA7",  # 𜵧 BLOCK OCTANT-23567
	b"\xF0\x9C\xB5\xA6",  # 𜵦 BLOCK OCTANT-13567
	b"\xF0\x9C\xB5\xA8",  # 𜵨 BLOCK OCTANT-123567
	b"\xF0\x9C\xB5\xAD",  # 𜵭 BLOCK OCTANT-34567
	b"\xF0\x9C\xB5\xAF",  # 𜵯 BLOCK OCTANT-234567
	b"\xF0\x9C\xB5\xAE",  # 𜵮 BLOCK OCTANT-134567
	b"\xF0\x9C\xB5\xB0",  # 𜵰 BLOCK OCTANT-1234567
	b"\xE2\x96\x82",      # ▂ LOWER ONE QUARTER BLOCK
	b"\xF0\x9C\xB6\xAD",  # 𜶭 BLOCK OCTANT-278
	b"\xF0\x9C\xB6\xAC",  # 𜶬 BLOCK OCTANT-178
	b"\xF0\x9C\xB6\xAE",  # 𜶮 BLOCK OCTANT-1278
	b"\xF0\x9C\xB6\xB3",  # 𜶳 BLOCK OCTANT-478
	b"\xF0\x9C\xB6\xB5",  # 𜶵 BLOCK OCTANT-2478
	b"\xF0\x9C\xB6\xB4",  # 𜶴 BLOCK OCTANT-1478
	b"\xF0\x9C\xB6\xB6",  # 𜶶 BLOCK OCTANT-12478
	b"\xF0\x9C\xB6\xAF",  # 𜶯 BLOCK OCTANT-378
	b"\xF0\x9C\xB6\xB1",  # 𜶱 BLOCK OCTANT-2378
	b"\xF0\x9C\xB6\xB0",  # 𜶰 BLOCK OCTANT-1378
	b"\xF0\x9C\xB6\xB2",  # 𜶲 BLOCK OCTANT-12378
	b"\xF0\x9C\xB6\xB7",  # 𜶷 BLOCK OCTANT-3478
	b"\xF0\x9C\xB6\xB9",  # 𜶹 BLOCK OCTANT-23478
	b"\xF0\x9C\xB6\xB8",  # 𜶸 BLOCK OCTANT-13478
	b"\xF0\x9C\xB6\xBA",  # 𜶺 BLOCK OCTANT-123478
	b"\xF0\x9C\xB7\x8B",  # 𜷋 BLOCK OCTANT-678
	b"\xF0\x9C\xB7\x8D",  # 𜷍 BLOCK OCTANT-2678
	b"\xF0\x9C\xB7\x8C",  # 𜷌 BLOCK OCTANT-1678
	b"\xF0\x9C\xB7\x8E",  # 𜷎 BLOCK OCTANT-12678
	b"\xF0\x9C\xB7\x93",  # 𜷓 BLOCK OCTANT-4678
	b"\xF0\x9C\xB7\x95",  # 𜷕 BLOCK OCTANT-24678
	b"\xF0\x9C\xB7\x94",  # 𜷔 BLOCK OCTANT-14678
	b"\xF0\x9C\xB7\x96",  # 𜷖 BLOCK OCTANT-124678
	b"\xF0\x9C\xB7\x8F",  # 𜷏 BLOCK OCTANT-3678
	b"\xF0\x9C\xB7\x91",  # 𜷑 BLOCK OCTANT-23678
	b"\xF0\x9C\xB7\x90",  # 𜷐 BLOCK OCTANT-13678
	b"\xF0\x9C\xB7\x92",  # 𜷒 BLOCK OCTANT-123678
	b"\xF0\x9C\xB7\x97",  # 𜷗 BLOCK OCTANT-34678
	b"\xF0\x9C\xB7\x99",  # 𜷙 BLOCK OCTANT-234678
	b"\xF0\x9C\xB7\x98",  # 𜷘 BLOCK OCTANT-134678
	b"\xF0\x9C\xB7\x9A",  # 𜷚 BLOCK OCTANT-1234678
	b"\xF0\x9C\xB6\xBB",  # 𜶻 BLOCK OCTANT-578
	b"\xF0\x9C\xB6\xBD",  # 𜶽 BLOCK OCTANT-2578
	b"\xF0\x9C\xB6\xBC",  # 𜶼 BLOCK OCTANT-1578
	b"\xF0\x9C\xB6\xBE",  # 𜶾 BLOCK OCTANT-12578
	b"\xF0\x9C\xB7\x83",  # 𜷃 BLOCK OCTANT-4578
	b"\xF0\x9C\xB7\x85",  # 𜷅 BLOCK OCTANT-24578
	b"\xF0\x9C\xB7\x84",  # 𜷄 BLOCK OCTANT-14578
	b"\xF0\x9C\xB7\x86",  # 𜷆 BLOCK OCTANT-124578
	b"\xF0\x9C\xB6\xBF",  # 𜶿 BLOCK OCTANT-3578
	b"\xF0\x9C\xB7\x81",  # 𜷁 BLOCK OCTANT-23578
	b"\xF0\x9C\xB7\x80",  # 𜷀 BLOCK OCTANT-13578
	b"\xF0\x9C\xB7\x82",  # 𜷂 BLOCK OCTANT-123578
	b"\xF0\x9C\xB7\x87",  # 𜷇 BLOCK OCTANT-34578
	b"\xF0\x9C\xB7\x89",  # 𜷉 BLOCK OCTANT-234578
	b"\xF0\x9C\xB7\x88",  # 𜷈 BLOCK OCTANT-134578
	b"\xF0\x9C\xB7\x8A",  # 𜷊 BLOCK OCTANT-1234578
	b"\xE2\x96\x84",      # ▄ LOWER HALF BLOCK
	b"\xF0\x9C\xB7\x9C",  # 𜷜 BLOCK OCTANT-25678
	b"\xF0\x9C\xB7\x9B",  # 𜷛 BLOCK OCTANT-15678
	b"\xF0\x9C\xB7\x9D",  # 𜷝 BLOCK OCTANT-125678
	b"\xF0\x9C\xB7\xA1",  # 𜷡 BLOCK OCTANT-45678
	b"\xE2\x96\x9F",      # ▟ QUADRANT UPPER RIGHT AND LOWER LEFT AND LOWER RIGHT
	b"\xF0\x9C\xB7\xA2",  # 𜷢 BLOCK OCTANT-145678
	b"\xF0\x9C\xB7\xA3",  # 𜷣 BLOCK OCTANT-1245678
	b"\xF0\x9C\xB7\x9E",  # 𜷞 BLOCK OCTANT-35678
	b"\xF0\x9C\xB7\x9F",  # 𜷟 BLOCK OCTANT-235678
	b"\xE2\x96\x99",      # ▙ QUADRANT UPPER LEFT AND LOWER LEFT AND LOWER RIGHT
	b"\xF0\x9C\xB7\xA0",  # 𜷠 BLOCK OCTANT-1235678
	b"\xE2\x96\x86",      # ▆ LOWER THREE QUARTERS BLOCK
	b"\xF0\x9C\xB7\xA5",  # 𜷥 BLOCK OCTANT-2345678
	b"\xF0\x9C\xB7\xA4",  # 𜷤 BLOCK OCTANT-1345678
	b"\xE2\x96\x88"       # █ FULL BLOCK
)

# Same as above, but using Braille dots
BRAILLE_MAP = (
    b"\xE2\xA0\x80",      # ⠀ BRAILLE PATTERN BLANK
    b"\xE2\xA0\x88",      # ⠈ BRAILLE PATTERN DOTS-4
    b"\xE2\xA0\x81",      # ⠁ BRAILLE PATTERN DOTS-1
    b"\xE2\xA0\x89",      # ⠉ BRAILLE PATTERN DOTS-14
    b"\xE2\xA0\x90",      # ⠐ BRAILLE PATTERN DOTS-5
    b"\xE2\xA0\x98",      # ⠘ BRAILLE PATTERN DOTS-45
    b"\xE2\xA0\x91",      # ⠑ BRAILLE PATTERN DOTS-15
    b"\xE2\xA0\x99",      # ⠙ BRAILLE PATTERN DOTS-145
    b"\xE2\xA0\x82",      # ⠂ BRAILLE PATTERN DOTS-2
    b"\xE2\xA0\x8A",      # ⠊ BRAILLE PATTERN DOTS-24
    b"\xE2\xA0\x83",      # ⠃ BRAILLE PATTERN DOTS-12
    b"\xE2\xA0\x8B",      # ⠋ BRAILLE PATTERN DOTS-124
    b"\xE2\xA0\x92",      # ⠒ BRAILLE PATTERN DOTS-25
    b"\xE2\xA0\x9A",      # ⠚ BRAILLE PATTERN DOTS-245
    b"\xE2\xA0\x93",      # ⠓ BRAILLE PATTERN DOTS-125
    b"\xE2\xA0\x9B",      # ⠛ BRAILLE PATTERN DOTS-1245
    b"\xE2\xA0\xA0",      # ⠠ BRAILLE PATTERN DOTS-6
    b"\xE2\xA0\xA8",      # ⠨ BRAILLE PATTERN DOTS-46
    b"\xE2\xA0\xA1",      # ⠡ BRAILLE PATTERN DOTS-16
    b"\xE2\xA0\xA9",      # ⠩ BRAILLE PATTERN DOTS-146
    b"\xE2\xA0\xB0",      # ⠰ BRAILLE PATTERN DOTS-56
    b"\xE2\xA0\xB8",      # ⠸ BRAILLE PATTERN DOTS-456
    b"\xE2\xA0\xB1",      # ⠱ BRAILLE PATTERN DOTS-156
    b"\xE2\xA0\xB9",      # ⠹ BRAILLE PATTERN DOTS-1456
    b"\xE2\xA0\xA2",      # ⠢ BRAILLE PATTERN DOTS-26
    b"\xE2\xA0\xAA",      # ⠪ BRAILLE PATTERN DOTS-246
    b"\xE2\xA0\xA3",      # ⠣ BRAILLE PATTERN DOTS-126
    b"\xE2\xA0\xAB",      # ⠫ BRAILLE PATTERN DOTS-1246
    b"\xE2\xA0\xB2",      # ⠲ BRAILLE PATTERN DOTS-256
    b"\xE2\xA0\xBA",      # ⠺ BRAILLE PATTERN DOTS-2456
    b"\xE2\xA0\xB3",      # ⠳ BRAILLE PATTERN DOTS-1256
    b"\xE2\xA0\xBB",      # ⠻ BRAILLE PATTERN DOTS-12456
    b"\xE2\xA0\x84",      # ⠄ BRAILLE PATTERN DOTS-3
    b"\xE2\xA0\x8C",      # ⠌ BRAILLE PATTERN DOTS-34
    b"\xE2\xA0\x85",      # ⠅ BRAILLE PATTERN DOTS-13
    b"\xE2\xA0\x8D",      # ⠍ BRAILLE PATTERN DOTS-134
    b"\xE2\xA0\x94",      # ⠔ BRAILLE PATTERN DOTS-35
    b"\xE2\xA0\x9C",      # ⠜ BRAILLE PATTERN DOTS-345
    b"\xE2\xA0\x95",      # ⠕ BRAILLE PATTERN DOTS-135
    b"\xE2\xA0\x9D",      # ⠝ BRAILLE PATTERN DOTS-1345
    b"\xE2\xA0\x86",      # ⠆ BRAILLE PATTERN DOTS-23
    b"\xE2\xA0\x8E",      # ⠎ BRAILLE PATTERN DOTS-234
    b"\xE2\xA0\x87",      # ⠇ BRAILLE PATTERN DOTS-123
    b"\xE2\xA0\x8F",      # ⠏ BRAILLE PATTERN DOTS-1234
    b"\xE2\xA0\x96",      # ⠖ BRAILLE PATTERN DOTS-235
    b"\xE2\xA0\x9E",      # ⠞ BRAILLE PATTERN DOTS-2345
    b"\xE2\xA0\x97",      # ⠗ BRAILLE PATTERN DOTS-1235
    b"\xE2\xA0\x9F",      # ⠟ BRAILLE PATTERN DOTS-12345
    b"\xE2\xA0\xA4",      # ⠤ BRAILLE PATTERN DOTS-36
    b"\xE2\xA0\xAC",      # ⠬ BRAILLE PATTERN DOTS-346
    b"\xE2\xA0\xA5",      # ⠥ BRAILLE PATTERN DOTS-136
    b"\xE2\xA0\xAD",      # ⠭ BRAILLE PATTERN DOTS-1346
    b"\xE2\xA0\xB4",      # ⠴ BRAILLE PATTERN DOTS-356
    b"\xE2\xA0\xBC",      # ⠼ BRAILLE PATTERN DOTS-3456
    b"\xE2\xA0\xB5",      # ⠵ BRAILLE PATTERN DOTS-1356
    b"\xE2\xA0\xBD",      # ⠽ BRAILLE PATTERN DOTS-13456
    b"\xE2\xA0\xA6",      # ⠦ BRAILLE PATTERN DOTS-236
    b"\xE2\xA0\xAE",      # ⠮ BRAILLE PATTERN DOTS-2346
    b"\xE2\xA0\xA7",      # ⠧ BRAILLE PATTERN DOTS-1236
    b"\xE2\xA0\xAF",      # ⠯ BRAILLE PATTERN DOTS-12346
    b"\xE2\xA0\xB6",      # ⠶ BRAILLE PATTERN DOTS-2356
    b"\xE2\xA0\xBE",      # ⠾ BRAILLE PATTERN DOTS-23456
    b"\xE2\xA0\xB7",      # ⠷ BRAILLE PATTERN DOTS-12356
    b"\xE2\xA0\xBF",      # ⠿ BRAILLE PATTERN DOTS-123456
    b"\xE2\xA2\x80",      # ⢀ BRAILLE PATTERN DOTS-8
    b"\xE2\xA2\x88",      # ⢈ BRAILLE PATTERN DOTS-48
    b"\xE2\xA2\x81",      # ⢁ BRAILLE PATTERN DOTS-18
    b"\xE2\xA2\x89",      # ⢉ BRAILLE PATTERN DOTS-148
    b"\xE2\xA2\x90",      # ⢐ BRAILLE PATTERN DOTS-58
    b"\xE2\xA2\x98",      # ⢘ BRAILLE PATTERN DOTS-458
    b"\xE2\xA2\x91",      # ⢑ BRAILLE PATTERN DOTS-158
    b"\xE2\xA2\x99",      # ⢙ BRAILLE PATTERN DOTS-1458
    b"\xE2\xA2\x82",      # ⢂ BRAILLE PATTERN DOTS-28
    b"\xE2\xA2\x8A",      # ⢊ BRAILLE PATTERN DOTS-248
    b"\xE2\xA2\x83",      # ⢃ BRAILLE PATTERN DOTS-128
    b"\xE2\xA2\x8B",      # ⢋ BRAILLE PATTERN DOTS-1248
    b"\xE2\xA2\x92",      # ⢒ BRAILLE PATTERN DOTS-258
    b"\xE2\xA2\x9A",      # ⢚ BRAILLE PATTERN DOTS-2458
    b"\xE2\xA2\x93",      # ⢓ BRAILLE PATTERN DOTS-1258
    b"\xE2\xA2\x9B",      # ⢛ BRAILLE PATTERN DOTS-12458
    b"\xE2\xA2\xA0",      # ⢠ BRAILLE PATTERN DOTS-68
    b"\xE2\xA2\xA8",      # ⢨ BRAILLE PATTERN DOTS-468
    b"\xE2\xA2\xA1",      # ⢡ BRAILLE PATTERN DOTS-168
    b"\xE2\xA2\xA9",      # ⢩ BRAILLE PATTERN DOTS-1468
    b"\xE2\xA2\xB0",      # ⢰ BRAILLE PATTERN DOTS-568
    b"\xE2\xA2\xB8",      # ⢸ BRAILLE PATTERN DOTS-4568
    b"\xE2\xA2\xB1",      # ⢱ BRAILLE PATTERN DOTS-1568
    b"\xE2\xA2\xB9",      # ⢹ BRAILLE PATTERN DOTS-14568
    b"\xE2\xA2\xA2",      # ⢢ BRAILLE PATTERN DOTS-268
    b"\xE2\xA2\xAA",      # ⢪ BRAILLE PATTERN DOTS-2468
    b"\xE2\xA2\xA3",      # ⢣ BRAILLE PATTERN DOTS-1268
    b"\xE2\xA2\xAB",      # ⢫ BRAILLE PATTERN DOTS-12468
    b"\xE2\xA2\xB2",      # ⢲ BRAILLE PATTERN DOTS-2568
    b"\xE2\xA2\xBA",      # ⢺ BRAILLE PATTERN DOTS-24568
    b"\xE2\xA2\xB3",      # ⢳ BRAILLE PATTERN DOTS-12568
    b"\xE2\xA2\xBB",      # ⢻ BRAILLE PATTERN DOTS-124568
    b"\xE2\xA2\x84",      # ⢄ BRAILLE PATTERN DOTS-38
    b"\xE2\xA2\x8C",      # ⢌ BRAILLE PATTERN DOTS-348
    b"\xE2\xA2\x85",      # ⢅ BRAILLE PATTERN DOTS-138
    b"\xE2\xA2\x8D",      # ⢍ BRAILLE PATTERN DOTS-1348
    b"\xE2\xA2\x94",      # ⢔ BRAILLE PATTERN DOTS-358
    b"\xE2\xA2\x9C",      # ⢜ BRAILLE PATTERN DOTS-3458
    b"\xE2\xA2\x95",      # ⢕ BRAILLE PATTERN DOTS-1358
    b"\xE2\xA2\x9D",      # ⢝ BRAILLE PATTERN DOTS-13458
    b"\xE2\xA2\x86",      # ⢆ BRAILLE PATTERN DOTS-238
    b"\xE2\xA2\x8E",      # ⢎ BRAILLE PATTERN DOTS-2348
    b"\xE2\xA2\x87",      # ⢇ BRAILLE PATTERN DOTS-1238
    b"\xE2\xA2\x8F",      # ⢏ BRAILLE PATTERN DOTS-12348
    b"\xE2\xA2\x96",      # ⢖ BRAILLE PATTERN DOTS-2358
    b"\xE2\xA2\x9E",      # ⢞ BRAILLE PATTERN DOTS-23458
    b"\xE2\xA2\x97",      # ⢗ BRAILLE PATTERN DOTS-12358
    b"\xE2\xA2\x9F",      # ⢟ BRAILLE PATTERN DOTS-123458
    b"\xE2\xA2\xA4",      # ⢤ BRAILLE PATTERN DOTS-368
    b"\xE2\xA2\xAC",      # ⢬ BRAILLE PATTERN DOTS-3468
    b"\xE2\xA2\xA5",      # ⢥ BRAILLE PATTERN DOTS-1368
    b"\xE2\xA2\xAD",      # ⢭ BRAILLE PATTERN DOTS-13468
    b"\xE2\xA2\xB4",      # ⢴ BRAILLE PATTERN DOTS-3568
    b"\xE2\xA2\xBC",      # ⢼ BRAILLE PATTERN DOTS-34568
    b"\xE2\xA2\xB5",      # ⢵ BRAILLE PATTERN DOTS-13568
    b"\xE2\xA2\xBD",      # ⢽ BRAILLE PATTERN DOTS-134568
    b"\xE2\xA2\xA6",      # ⢦ BRAILLE PATTERN DOTS-2368
    b"\xE2\xA2\xAE",      # ⢮ BRAILLE PATTERN DOTS-23468
    b"\xE2\xA2\xA7",      # ⢧ BRAILLE PATTERN DOTS-12368
    b"\xE2\xA2\xAF",      # ⢯ BRAILLE PATTERN DOTS-123468
    b"\xE2\xA2\xB6",      # ⢶ BRAILLE PATTERN DOTS-23568
    b"\xE2\xA2\xBE",      # ⢾ BRAILLE PATTERN DOTS-234568
    b"\xE2\xA2\xB7",      # ⢷ BRAILLE PATTERN DOTS-123568
    b"\xE2\xA2\xBF",      # ⢿ BRAILLE PATTERN DOTS-1234568
    b"\xE2\xA1\x80",      # ⡀ BRAILLE PATTERN DOTS-7
    b"\xE2\xA1\x88",      # ⡈ BRAILLE PATTERN DOTS-47
    b"\xE2\xA1\x81",      # ⡁ BRAILLE PATTERN DOTS-17
    b"\xE2\xA1\x89",      # ⡉ BRAILLE PATTERN DOTS-147
    b"\xE2\xA1\x90",      # ⡐ BRAILLE PATTERN DOTS-57
    b"\xE2\xA1\x98",      # ⡘ BRAILLE PATTERN DOTS-457
    b"\xE2\xA1\x91",      # ⡑ BRAILLE PATTERN DOTS-157
    b"\xE2\xA1\x99",      # ⡙ BRAILLE PATTERN DOTS-1457
    b"\xE2\xA1\x82",      # ⡂ BRAILLE PATTERN DOTS-27
    b"\xE2\xA1\x8A",      # ⡊ BRAILLE PATTERN DOTS-247
    b"\xE2\xA1\x83",      # ⡃ BRAILLE PATTERN DOTS-127
    b"\xE2\xA1\x8B",      # ⡋ BRAILLE PATTERN DOTS-1247
    b"\xE2\xA1\x92",      # ⡒ BRAILLE PATTERN DOTS-257
    b"\xE2\xA1\x9A",      # ⡚ BRAILLE PATTERN DOTS-2457
    b"\xE2\xA1\x93",      # ⡓ BRAILLE PATTERN DOTS-1257
    b"\xE2\xA1\x9B",      # ⡛ BRAILLE PATTERN DOTS-12457
    b"\xE2\xA1\xA0",      # ⡠ BRAILLE PATTERN DOTS-67
    b"\xE2\xA1\xA8",      # ⡨ BRAILLE PATTERN DOTS-467
    b"\xE2\xA1\xA1",      # ⡡ BRAILLE PATTERN DOTS-167
    b"\xE2\xA1\xA9",      # ⡩ BRAILLE PATTERN DOTS-1467
    b"\xE2\xA1\xB0",      # ⡰ BRAILLE PATTERN DOTS-567
    b"\xE2\xA1\xB8",      # ⡸ BRAILLE PATTERN DOTS-4567
    b"\xE2\xA1\xB1",      # ⡱ BRAILLE PATTERN DOTS-1567
    b"\xE2\xA1\xB9",      # ⡹ BRAILLE PATTERN DOTS-14567
    b"\xE2\xA1\xA2",      # ⡢ BRAILLE PATTERN DOTS-267
    b"\xE2\xA1\xAA",      # ⡪ BRAILLE PATTERN DOTS-2467
    b"\xE2\xA1\xA3",      # ⡣ BRAILLE PATTERN DOTS-1267
    b"\xE2\xA1\xAB",      # ⡫ BRAILLE PATTERN DOTS-12467
    b"\xE2\xA1\xB2",      # ⡲ BRAILLE PATTERN DOTS-2567
    b"\xE2\xA1\xBA",      # ⡺ BRAILLE PATTERN DOTS-24567
    b"\xE2\xA1\xB3",      # ⡳ BRAILLE PATTERN DOTS-12567
    b"\xE2\xA1\xBB",      # ⡻ BRAILLE PATTERN DOTS-124567
    b"\xE2\xA1\x84",      # ⡄ BRAILLE PATTERN DOTS-37
    b"\xE2\xA1\x8C",      # ⡌ BRAILLE PATTERN DOTS-347
    b"\xE2\xA1\x85",      # ⡅ BRAILLE PATTERN DOTS-137
    b"\xE2\xA1\x8D",      # ⡍ BRAILLE PATTERN DOTS-1347
    b"\xE2\xA1\x94",      # ⡔ BRAILLE PATTERN DOTS-357
    b"\xE2\xA1\x9C",      # ⡜ BRAILLE PATTERN DOTS-3457
    b"\xE2\xA1\x95",      # ⡕ BRAILLE PATTERN DOTS-1357
    b"\xE2\xA1\x9D",      # ⡝ BRAILLE PATTERN DOTS-13457
    b"\xE2\xA1\x86",      # ⡆ BRAILLE PATTERN DOTS-237
    b"\xE2\xA1\x8E",      # ⡎ BRAILLE PATTERN DOTS-2347
    b"\xE2\xA1\x87",      # ⡇ BRAILLE PATTERN DOTS-1237
    b"\xE2\xA1\x8F",      # ⡏ BRAILLE PATTERN DOTS-12347
    b"\xE2\xA1\x96",      # ⡖ BRAILLE PATTERN DOTS-2357
    b"\xE2\xA1\x9E",      # ⡞ BRAILLE PATTERN DOTS-23457
    b"\xE2\xA1\x97",      # ⡗ BRAILLE PATTERN DOTS-12357
    b"\xE2\xA1\x9F",      # ⡟ BRAILLE PATTERN DOTS-123457
    b"\xE2\xA1\xA4",      # ⡤ BRAILLE PATTERN DOTS-367
    b"\xE2\xA1\xAC",      # ⡬ BRAILLE PATTERN DOTS-3467
    b"\xE2\xA1\xA5",      # ⡥ BRAILLE PATTERN DOTS-1367
    b"\xE2\xA1\xAD",      # ⡭ BRAILLE PATTERN DOTS-13467
    b"\xE2\xA1\xB4",      # ⡴ BRAILLE PATTERN DOTS-3567
    b"\xE2\xA1\xBC",      # ⡼ BRAILLE PATTERN DOTS-34567
    b"\xE2\xA1\xB5",      # ⡵ BRAILLE PATTERN DOTS-13567
    b"\xE2\xA1\xBD",      # ⡽ BRAILLE PATTERN DOTS-134567
    b"\xE2\xA1\xA6",      # ⡦ BRAILLE PATTERN DOTS-2367
    b"\xE2\xA1\xAE",      # ⡮ BRAILLE PATTERN DOTS-23467
    b"\xE2\xA1\xA7",      # ⡧ BRAILLE PATTERN DOTS-12367
    b"\xE2\xA1\xAF",      # ⡯ BRAILLE PATTERN DOTS-123467
    b"\xE2\xA1\xB6",      # ⡶ BRAILLE PATTERN DOTS-23567
    b"\xE2\xA1\xBE",      # ⡾ BRAILLE PATTERN DOTS-234567
    b"\xE2\xA1\xB7",      # ⡷ BRAILLE PATTERN DOTS-123567
    b"\xE2\xA1\xBF",      # ⡿ BRAILLE PATTERN DOTS-1234567
    b"\xE2\xA3\x80",      # ⣀ BRAILLE PATTERN DOTS-78
    b"\xE2\xA3\x88",      # ⣈ BRAILLE PATTERN DOTS-478
    b"\xE2\xA3\x81",      # ⣁ BRAILLE PATTERN DOTS-178
    b"\xE2\xA3\x89",      # ⣉ BRAILLE PATTERN DOTS-1478
    b"\xE2\xA3\x90",      # ⣐ BRAILLE PATTERN DOTS-578
    b"\xE2\xA3\x98",      # ⣘ BRAILLE PATTERN DOTS-4578
    b"\xE2\xA3\x91",      # ⣑ BRAILLE PATTERN DOTS-1578
    b"\xE2\xA3\x99",      # ⣙ BRAILLE PATTERN DOTS-14578
    b"\xE2\xA3\x82",      # ⣂ BRAILLE PATTERN DOTS-278
    b"\xE2\xA3\x8A",      # ⣊ BRAILLE PATTERN DOTS-2478
    b"\xE2\xA3\x83",      # ⣃ BRAILLE PATTERN DOTS-1278
    b"\xE2\xA3\x8B",      # ⣋ BRAILLE PATTERN DOTS-12478
    b"\xE2\xA3\x92",      # ⣒ BRAILLE PATTERN DOTS-2578
    b"\xE2\xA3\x9A",      # ⣚ BRAILLE PATTERN DOTS-24578
    b"\xE2\xA3\x93",      # ⣓ BRAILLE PATTERN DOTS-12578
    b"\xE2\xA3\x9B",      # ⣛ BRAILLE PATTERN DOTS-124578
    b"\xE2\xA3\xA0",      # ⣠ BRAILLE PATTERN DOTS-678
    b"\xE2\xA3\xA8",      # ⣨ BRAILLE PATTERN DOTS-4678
    b"\xE2\xA3\xA1",      # ⣡ BRAILLE PATTERN DOTS-1678
    b"\xE2\xA3\xA9",      # ⣩ BRAILLE PATTERN DOTS-14678
    b"\xE2\xA3\xB0",      # ⣰ BRAILLE PATTERN DOTS-5678
    b"\xE2\xA3\xB8",      # ⣸ BRAILLE PATTERN DOTS-45678
    b"\xE2\xA3\xB1",      # ⣱ BRAILLE PATTERN DOTS-15678
    b"\xE2\xA3\xB9",      # ⣹ BRAILLE PATTERN DOTS-145678
    b"\xE2\xA3\xA2",      # ⣢ BRAILLE PATTERN DOTS-2678
    b"\xE2\xA3\xAA",      # ⣪ BRAILLE PATTERN DOTS-24678
    b"\xE2\xA3\xA3",      # ⣣ BRAILLE PATTERN DOTS-12678
    b"\xE2\xA3\xAB",      # ⣫ BRAILLE PATTERN DOTS-124678
    b"\xE2\xA3\xB2",      # ⣲ BRAILLE PATTERN DOTS-25678
    b"\xE2\xA3\xBA",      # ⣺ BRAILLE PATTERN DOTS-245678
    b"\xE2\xA3\xB3",      # ⣳ BRAILLE PATTERN DOTS-125678
    b"\xE2\xA3\xBB",      # ⣻ BRAILLE PATTERN DOTS-1245678
    b"\xE2\xA3\x84",      # ⣄ BRAILLE PATTERN DOTS-378
    b"\xE2\xA3\x8C",      # ⣌ BRAILLE PATTERN DOTS-3478
    b"\xE2\xA3\x85",      # ⣅ BRAILLE PATTERN DOTS-1378
    b"\xE2\xA3\x8D",      # ⣍ BRAILLE PATTERN DOTS-13478
    b"\xE2\xA3\x94",      # ⣔ BRAILLE PATTERN DOTS-3578
    b"\xE2\xA3\x9C",      # ⣜ BRAILLE PATTERN DOTS-34578
    b"\xE2\xA3\x95",      # ⣕ BRAILLE PATTERN DOTS-13578
    b"\xE2\xA3\x9D",      # ⣝ BRAILLE PATTERN DOTS-134578
    b"\xE2\xA3\x86",      # ⣆ BRAILLE PATTERN DOTS-2378
    b"\xE2\xA3\x8E",      # ⣎ BRAILLE PATTERN DOTS-23478
    b"\xE2\xA3\x87",      # ⣇ BRAILLE PATTERN DOTS-12378
    b"\xE2\xA3\x8F",      # ⣏ BRAILLE PATTERN DOTS-123478
    b"\xE2\xA3\x96",      # ⣖ BRAILLE PATTERN DOTS-23578
    b"\xE2\xA3\x9E",      # ⣞ BRAILLE PATTERN DOTS-234578
    b"\xE2\xA3\x97",      # ⣗ BRAILLE PATTERN DOTS-123578
    b"\xE2\xA3\x9F",      # ⣟ BRAILLE PATTERN DOTS-1234578
    b"\xE2\xA3\xA4",      # ⣤ BRAILLE PATTERN DOTS-3678
    b"\xE2\xA3\xAC",      # ⣬ BRAILLE PATTERN DOTS-34678
    b"\xE2\xA3\xA5",      # ⣥ BRAILLE PATTERN DOTS-13678
    b"\xE2\xA3\xAD",      # ⣭ BRAILLE PATTERN DOTS-134678
    b"\xE2\xA3\xB4",      # ⣴ BRAILLE PATTERN DOTS-35678
    b"\xE2\xA3\xBC",      # ⣼ BRAILLE PATTERN DOTS-345678
    b"\xE2\xA3\xB5",      # ⣵ BRAILLE PATTERN DOTS-135678
    b"\xE2\xA3\xBD",      # ⣽ BRAILLE PATTERN DOTS-1345678
    b"\xE2\xA3\xA6",      # ⣦ BRAILLE PATTERN DOTS-23678
    b"\xE2\xA3\xAE",      # ⣮ BRAILLE PATTERN DOTS-234678
    b"\xE2\xA3\xA7",      # ⣧ BRAILLE PATTERN DOTS-123678
    b"\xE2\xA3\xAF",      # ⣯ BRAILLE PATTERN DOTS-1234678
    b"\xE2\xA3\xB6",      # ⣶ BRAILLE PATTERN DOTS-235678
    b"\xE2\xA3\xBE",      # ⣾ BRAILLE PATTERN DOTS-2345678
    b"\xE2\xA3\xB7",      # ⣷ BRAILLE PATTERN DOTS-1235678
    b"\xE2\xA3\xBF"       # ⣿ BRAILLE PATTERN DOTS-12345678
)


# This mapping table tells us how many UTF-8 bytes a single character can
# require for each pseudo-pixels type. This is used to provide the FLF2
# header with the buffer size it needs to safely store the longest line of
# its contained FIGlet characters.
# This is needed because the FLF2 header specifies that size in bytes, not
# characters, and when using UTF-8, characters can be 1, 2, 3, or 4 bytes.
MAX_BYTES_PER_CHAR = {
	1:  3,  # Full-blocks
	2:  3,  # Half-blocks
	4:  3,  # Quadrants
	6:  4,  # Sextants
	8:  4,  # Octants
	24: 4,  # Separated Quadrants
	26: 4,  # Separated Sextants
	28: 3   # Braille
}


# Helper to find which characters map to use for a specific pixels_per_character type.
PSEUDOPIXELS_MAPS = {
    1:  FULLBLOCK_MAP,
    2:  HALFBLOCK_MAP,
    4:  QUADRANT_MAP,
    6:  SEXTANT_MAP,
    8:  OCTANT_MAP,
	24: SEPARATED_QUADRANT_MAP,
	26: SEPARATED_SEXTANT_MAP,
	28: BRAILLE_MAP
}


# Our main FIGlet characters renderer function, used by generate_flf2 to convert a normalized BDF bitmap to a FLF2 character
def bmp_to_figchar(bmp, height, width, pixels_per_character, horizontal_pixels_per_char, vertical_pixels_per_char):
	"""
	Convert a BDF-style bitmap to a FIGlet character UTF-8 bytearray.
	The pixels_per_character argument can only be 1, 2, 4, 6, or 8.
	The return value are the bytes for the FLF2 character entry.
	"""
	# This simply breaks a larger bitmap into mosaic tiles, and converts them into a single UTF-8 bytes sequence in FLF2 format.
	figchar = bytearray()
	clines = len(bmp)
	for y in range(0, height, vertical_pixels_per_char):
		for x in range(0, width, horizontal_pixels_per_char):
			if pixels_per_character == 1:
				hoffset = width - (x+1)  # the shift needed to align the pixel we need
				bit = (bmp[y] >> hoffset) & 0b1
				figchar.extend(FULLBLOCK_MAP[bit])
			elif pixels_per_character == 2:
				hoffset = width - (x+1)  # the shift needed to align the pixel we need
				chrbmp = [0, 0]
				if y < clines:
					chrbmp[0] = (bmp[y] >> hoffset) & 0b1
				if (vertical_pixels_per_char > 1) and (y+1 < clines):
					chrbmp[1] = (bmp[y+1] >> hoffset) & 0b1
				bits = (chrbmp[0]) | (chrbmp[1] << 1)
				figchar.extend(HALFBLOCK_MAP[bits])
			else:
				hoffset = width - (x+2)  # the shift needed to align the two pixels we need
				chrbmp = [0, 0, 0, 0] # max height is 4 for octants, others ignore extra lines
				if y < clines:
					chrbmp[0] = (bmp[y] >> hoffset) & 0b11
				if (vertical_pixels_per_char > 1) and (y+1 < clines):
					chrbmp[1] = (bmp[y+1] >> hoffset) & 0b11
				if (vertical_pixels_per_char > 2) and (y+2 < clines):
					chrbmp[2] = (bmp[y+2] >> hoffset) & 0b11
				if (vertical_pixels_per_char > 3) and (y+3 < clines):
					chrbmp[3] = (bmp[y+3] >> hoffset) & 0b11
				
				bits = (chrbmp[0]) | (chrbmp[1] << 2) | (chrbmp[2] << 4) | (chrbmp[3] << 6)
				chars_map = PSEUDOPIXELS_MAPS[pixels_per_character]
				figchar.extend(chars_map[bits])
		if y+vertical_pixels_per_char < height:
			figchar.extend(b"\x40\x0A") # FIGlet EOL @ + newline
		else:
			figchar.extend(b"\x40\x40\x0A") # FIGlet EOL @@ + newline
	return bytes(figchar)



############################################################################
#
# This second part is a BDF parser that converts a BDF file into the
# objects we'll need to generate the corresponding FLF2 file.
#


# This function parses a .bdf file and creates a font object containing the fields we need.
def parse_bdf(path):
	"""
	Parse a BDF file into a font object.
	"""

	font = {
		"pixel_size": None,   # global font height
		"glyphs": {}
	}

	pixel_size = None
	font_ascent = None
	font_descent = None
	font_bbox = None  # (w, h, xoff, yoff)

	with open(path, "r", encoding="utf-8", errors="replace") as f:
		lines = f.readlines()

	i = 0
	n = len(lines)

	while i < n:
		line = lines[i].strip()

		# PIXEL_SIZE (preferred if present)
		if line.startswith("PIXEL_SIZE"):
			parts = line.split()
			pixel_size = int(parts[1])

		elif line.startswith("FONT_ASCENT"):
			parts = line.split()
			font_ascent = int(parts[1])

		elif line.startswith("FONT_DESCENT"):
			parts = line.split()
			font_descent = int(parts[1])

		# FONTBOUNDINGBOX w h xoff yoff
		elif line.startswith("FONTBOUNDINGBOX"):
			parts = line.split()
			w  = int(parts[1])
			h  = int(parts[2])
			xo = int(parts[3])
			yo = int(parts[4])
			font_bbox = (w, h, xo, yo)

		# STARTCHAR block
		# This is the beginning of a character section,
		# we need another parser until we reach ENDCHAR.
		elif line.startswith("STARTCHAR"):
			glyph_name = line.split(maxsplit=1)[1]

			encoding = None
			bbx = None
			bitmap = []

			i += 1
			while i < n:
				line = lines[i].strip()

				if line.startswith("ENCODING"):
					encoding = int(line.split()[1])

				elif line.startswith("DWIDTH"):
					parts = line.split()
					dwidth = int(parts[1], 10)

				elif line.startswith("BBX"):
					parts = line.split()
					bbx = (
						int(parts[1]),  # width
						int(parts[2]),  # height
						int(parts[3]),  # xoff
						int(parts[4])   # yoff
					)

				elif line == "BITMAP":
					i += 1
					while i < n:
						hexline = lines[i].strip()
						if hexline == "ENDCHAR":
							break
						bitmap.append(int(hexline, 16))
						i += 1
					break

				i += 1

			# Store the character in our font's glyphs collection
			font["glyphs"][encoding] = {
				"name": glyph_name,
				"bbx": bbx,
				"bitmap": bitmap,
				"dwidth": dwidth,
			}

		i += 1

	# Decide global font height
	if pixel_size is not None:
		# If a pixel-size was found, use that
		font["pixel_size"] = pixel_size

		# Some fonts have mismatched pixel_size/font_ascent/font_descent and font_bbox values,
		# check for that situation and adjust the font_bbox to trust the pixel_size and
		# explicit ascent and descent instead for our conversions.

		if font_descent is None and font_bbox is not None:
			font_descent = -font_bbox[3] # use the bounding box y offset as the descent
		
		if font_descent is not None:
			if font_bbox is not None:
				# Adjust the font bounding box to match explicit dimensions
				width, height, xoff, yoff = font_bbox
				font["font_bbox"] = (width, pixel_size, xoff, -font_descent)
			else:
				# Create a font bounding box without any mininum width
				font["font_bbox"] = (0, pixel_size, 0, -font_descent)
		else:
			# Fallback if both FONTBOUNDINGBOX and FONT_DESCENT are missing
			# Create a font bounding box without any minium width and with bottom-valigned
			font["font_bbox"] = (0, pixel_size, 0, 0)
	elif font_bbox is not None:
		# Otherwise, use the font bounding box height as its pixel_size
		_, height, _, yoff = font_bbox
		font["pixel_size"] = height - abs(yoff)
		font["font_bbox"] = font_bbox
	else:
		raise ValueError("No PIXEL_SIZE or FONTBOUNDINGBOX found in BDF to decide the font height.")

	return font


# This function removes any control character that might have been included in the glyph collection of a font object
def remove_control_characters(font):
	"""
	Remove any control character (C0, DELETE, C1) from the font object.
	"""
	glyphs = font["glyphs"]

	# C0 block: 0x00 - 0x1F
	for cp in range(0x00, 0x20):
		if cp in glyphs:
			del glyphs[cp]

	# DELETE: 0x7F
	if 0x7F in glyphs:
		del glyphs[0x7F]

	# C1 block: 0x80 - 0x9F
	for cp in range(0x80, 0xA0):
		if cp in glyphs:
			del glyphs[cp]



############################################################################
#
# This third part contains functions to normalize BDF bitmaps.
# 
# The goal is to apply (bake-in) the BBX (bitmap bounding box and offset)
# so the bitmaps are all using the same canvas and take care of things such
# as overhang if requested, extending the bitmaps as needed.
# It also prepared the bitmaps to fit the requirements of the requested
# mosaics export, forcing them into multiples of 1x1, 1x2, 2x2, 2x3, or 2x4.
# 

def normalize_bitmaps(font, fit_horizontal_overhang, horizontal_pixels_per_char, vertical_pixels_per_char):
	"""
	Normalize BDF bitmaps into a fixed FIGlet-compatible canvas,
	preserving baseline alignment and applying optional overhang-aware
	horizontal expansion.
	"""

	font_bbox = font["font_bbox"]
	font_w, font_h, font_xoff, font_yoff = font_bbox
	font_height = font["pixel_size"]

	# We keep a maximum width of the whole font because we need this for the FLF2 header
	global_max_width = 0

	# Target canvas height
	target_height = (font_height + (vertical_pixels_per_char - 1)) // vertical_pixels_per_char * vertical_pixels_per_char

	# Baseline mapping
	global_ascent  = font_h + font_yoff
	global_descent = -font_yoff
	
	target_ascent  = (target_height * global_ascent) // font_h
	target_descent = target_height - target_ascent

	padding_bottom = max(0, target_descent - global_descent)

	for cp, glyph in font["glyphs"].items():
		bbx_width, bbx_height, xoff, yoff = glyph["bbx"]
		dwidth = glyph["dwidth"]
		source_bitmap = glyph["bitmap"]

		bits_per_row = ((bbx_width + 7) // 8) * 8 # This is the stride of each pixels row
		bitspadding = bits_per_row - bbx_width # This is the padding of unused bits on the right

		# Some files have bitmap values with garbage after the actual pixels in the unused bits.
		# So we should trim them to keep only the valid bits.
		# Compute a mask to AND with the values to discard any garbage bit.
		bbxmask = ((1 << bbx_width) - 1) << bitspadding;
		
		if fit_horizontal_overhang:
			# Original window for the bitmap as designed with its designed bounding box.
			# This is the bounding box we need to keep at a minimum even if it could be tighter.
			orig_min_x = -xoff
			orig_max_x = dwidth - 1 - xoff

			# We start with the window already reaching at least those borders
			min_x = orig_min_x
			max_x = orig_max_x

			for row_int in source_bitmap:
				# Discard any garbage bit outside of the bounding box
				row_int &= bbxmask;

				# Guard against rows with no pixels, as the following code cannot handle those
				if row_int == 0:
					continue
				
				# Find positions of first and last pixels in full stride
				left_idx = bits_per_row - row_int.bit_length()
				right_idx = bits_per_row - ((row_int & -row_int).bit_length())
				
				# Keep the furthest values
				min_x = min(min_x, left_idx)
				max_x = max(max_x, right_idx)

			# Compute extensions relative to original window
			extend_left  = max(0, orig_min_x - min_x)
			extend_right = max(0, max_x - orig_max_x)

			# If no extension is needed, keep xoff/dwidth as designed in font
			if extend_left > 0 or extend_right > 0:
				if (horizontal_pixels_per_char > 1) and ((extend_right%2) or (extend_left%2)):
					# If we have to extend by a multiple of 2 for the target mosaics but
					# the character only needed extension by 1 pixel, we should tweak
					# the position to keep the proximity to the surrounding characters
					# proportional to their original intent. For example if it must be
					# shifted right by 1px, but we extended by 2px, we should shift by
					# 2 to keep it closer to the character on its right as originally
					# designed.
					xoff += 1
					extend_right += 1

				# Adjust dwidth and xoff according to extended window
				dwidth = dwidth + extend_left + extend_right
				xoff = xoff + extend_left

		# Horizontal rounding
		target_width = (dwidth + (horizontal_pixels_per_char - 1)) // horizontal_pixels_per_char * horizontal_pixels_per_char

		# Vertical placement
		top_row = target_height - (yoff + bbx_height) + font_yoff - padding_bottom
		target_bitmap = [0] * target_height


		# Bake bitmap into canvas with our new window
		# We must shift all rows by the xoff horizontal offset,
		# and righ-align the bitmap.
		cshift = bits_per_row - (target_width - xoff)
		
		for i in range(bbx_height):
			row_int = source_bitmap[i]

			# Discard any garbage bit outside of the bounding box
			row_int &= bbxmask;

			if row_int == 0:
				continue

			canvas_y = top_row + i
			if not (0 <= canvas_y < target_height):
				continue

			# Shift horizontally according to xoff horizontal offset
			if cshift > 0:
				row_int >>= cshift
			elif cshift < 0:
				row_int <<= -cshift

			# Store shifted row in bitmap
			target_bitmap[canvas_y] = row_int

		glyph["bitmap"] = target_bitmap
		glyph["dwidth"] = target_width
		del glyph["bbx"]

		global_max_width = max(global_max_width, target_width)

	font["max_width"] = global_max_width
	font["flf2_baseline"] = (target_ascent + vertical_pixels_per_char // 2) // vertical_pixels_per_char


############################################################################
#
# This fourth part is a FLF2 (FIGlet) exporter.
# 
# It uses the font object we processed and normalized and simply generate a
# FLF2 font from its contents.
#


def zip_in_place(path):
	"""
	Compress a FLF2 file in-place, replacing the uncompressed version with the compressed one.
	"""
	# Create a temporary file in the same directory
	dirpath = os.path.dirname(path)
	fd, tmp = tempfile.mkstemp(dir=dirpath)
	os.close(fd)

	try:
		# Write the .flf file in the archive
		with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
			z.write(path, arcname=os.path.basename(path))

		# Atomic replace
		shutil.move(tmp, path)
	finally:
		# If something failed, ensure temp is removed
		if os.path.exists(tmp):
			os.remove(tmp)


def generate_flf2(path, font, comment, compressed, include_char_names, pixels_per_character, horizontal_pixels_per_char, vertical_pixels_per_char):
	"""
	Create a FLF2 file from a specified font object.
	"""

	glyphs = font["glyphs"]

	# Compute FIGcharacter height in lines from any character
	glyph_height = (font["pixel_size"] + (vertical_pixels_per_char-1)) // vertical_pixels_per_char

	# Get number of characters in font
	glyphs_count = len([cp for cp in glyphs])

	with open(path, "wb") as f:

		# FLF2 Header
		hardblank = "$" # We don't use smushing with octants, so it can be anything
		height = glyph_height # Computed above, this is the number of lines of the FIGfont
		baseline = font["flf2_baseline"] # Computed during normalize_bitmaps
		old_layout = -1 # Full-width layout
		comment_lines = len(comment) + 2 # Compute number of comment and generator+timestamp lines
		print_direction = 0 # LTR (use 1 for RTL)
		full_layout = 0 # No smushing applied
		codetag_count = glyphs_count - 102 # Number of extra characters after ASCII and German
		# Compute the max_length for this FLF2 file
		# It must be at last the width of the widest FIGcharacter, plus 2 to accommodate endmarks
		# We computed the widest bitmap in normalize_bitmaps and stored it in font["max_width"].
		max_length = (
			# Number of characters of the longest line
			# This is the ceil(max_width / horizontal_pixels_per_char)
			((font["max_width"] + (horizontal_pixels_per_char-1))//horizontal_pixels_per_char)
			# Max number of bytes per character in UTF-8 encoding
			* MAX_BYTES_PER_CHAR[pixels_per_character]
			# Plus FIGlet end-of-line marker "@@"
			+ 2
			# FIGlet specs states trailing \n should not be counted
		)
		# Build header string
		header = (
			f"flf2a{hardblank} {height} {baseline} {max_length} "
			f"{old_layout} {comment_lines} {print_direction} "
			f"{full_layout} {codetag_count}\n"
		)
		f.write(header.encode("ascii"))

		# Comment section
		f.write(b"".join(line.encode("utf-8") for line in comment))
		# Generator and timestamp
		f.write(("Generated by Philippe Majerus's phm_bdf2flf.py on "
					+ datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
					+ " UTC\n\n").encode("utf-8"))

		# ASCII section
		for cp in range(32, 127):
			glyph = glyphs.get(cp)
			if glyph is None:
				raise ValueError(f"Missing required character U+{cp:04X}.")
			else:
				f.write(bmp_to_figchar(glyph["bitmap"], glyph_height*vertical_pixels_per_char, glyph["dwidth"], pixels_per_character, horizontal_pixels_per_char, vertical_pixels_per_char))
				# Remove from map so extras won't include it
				del glyphs[cp]

		# Legacy German section
		for cp in (0x00C4, 0x00D6, 0x00DC, 0x00E4, 0x00F6, 0x00FC, 0x00DF):
			glyph = glyphs.get(cp)
			if glyph is None:
				raise ValueError(f"Missing required character U+{cp:04X}.")
			else:
				f.write(bmp_to_figchar(glyph["bitmap"], glyph_height*vertical_pixels_per_char, glyph["dwidth"], pixels_per_character, horizontal_pixels_per_char, vertical_pixels_per_char))
				# Remove from map so extras won't include it
				del glyphs[cp]

		# Extra code units section
		for cp in sorted(glyphs):
			glyph = glyphs[cp]
			if cp == 0:
				# Provide a cleaner index format for special character
				# because it isn't a Unicode code point
				if include_char_names:
					f.write("0 FIGlet missing character\n".encode("utf-8"))
				else:
					f.write("0\n".encode("ascii"))
			else:
				# Format normal Unicode-style code point
				if include_char_names:
					name = glyph["name"]
					f.write(f"0x{cp:04X} {name}\n".encode("utf-8"))
				else:
					f.write(f"0x{cp:04X}\n".encode("ascii"))
			f.write(bmp_to_figchar(glyph["bitmap"], glyph_height*vertical_pixels_per_char, glyph["dwidth"], pixels_per_character, horizontal_pixels_per_char, vertical_pixels_per_char))

	if compressed:
		# UTF-8-encoded octants are using 4 bytes for most of its character set
		# taking advantage of FIGlet's compressed .flf support basically makes
		# our font four times smaller.
		zip_in_place(path)

	return glyphs_count



############################################################################
#
# This is the main code of this script
# We parse the BDF file, perform some processing & tweaking, and export FLF2.
#


# Provide optional descriptive names for pixels_per_character argument.
class PixelsPerCharacter(IntEnum):
	FULLBLOCK = 1             # Requires Unicode 1.1
	HALFBLOCK = 2             # Requires Unicode 1.1
	QUADRANTS = 4             # Requires Unicode 3.2
	SEXTANTS = 6              # Requires Unicode 13.0 Symbols for Legacy Computing block
	OCTANTS = 8               # Requires Unicode 16.0 Symbols for Legacy Computing Supplement block
	SEPARATED_QUADRANTS = 24  # Requires Unicode 16.0 Symbols for Legacy Computing Supplement block
	SEPARATED_SEXTANTS = 26   # Requires Unicode 16.0 Symbols for Legacy Computing Supplement block
	BRAILLE = 28              # Requires Unicode 3.0 Braille block


# This is our main conversion function, provide it with the path to BDF file,
# path of FIGlet file to generate, and whether the .flf should be compressed,
# and whether horizontal overhang should extend the bitmaps or be cropped.
# This should be the only function you need to import from this script file
# to handle the BDF to FIGlet conversion.
def build_flf2(bdfpath, flfpath, comment = [], compressed = True, pixels_per_character: PixelsPerCharacter = PixelsPerCharacter.OCTANTS, fit_horizontal_overhang = True, missing_character = None, include_char_names = False):
	"""
	DBF to FLF2 conversion utility, takes a BDF and some optional parameters, and creates the corresponding pseudo-pixels-based FIGlet font.
	See the phm_bdf2flf.py file for more details and usage example.
	"""
	print()
	print("BDF to pseudo-pixels/mosaics FIGlet export script by Philippe Majerus")

	# Validate pseudo-pixels type requested
	if pixels_per_character not in [1, 2, 4, 6, 8, 24, 26, 28]:
		raise ValueError(f"pixels_per_character must be 1, 2, 4, 6, 8, 24, 26, or 28 not {pixels_per_character}.")
	# Compute FLF2 characters dimensions
	vertical_pixels_per_char = pixels_per_character if pixels_per_character <= 2 else ((pixels_per_character%20)//2)
	horizontal_pixels_per_char = 1 if pixels_per_character <= 2 else 2

	print("Parsing BDF file "+ bdfpath +"...")

	# Load metadata and characters from BDF file
	font = parse_bdf(bdfpath)

	# Remove any control character defined in the BDF file
	remove_control_characters(font)

	# Set the FIGlet missing character (tofu) if provided
	if missing_character is not None:
		# We need to perform a copy because we're going to
		# modify it when processing glyphs and the caller
		# might not expect us to change it and use the same
		# character object for several conversions.
		font["glyphs"][0] = copy.deepcopy(missing_character)

	print("Processing glyphs...")

	# Normalize bitmaps to their required dimensions
	# We also extend the target bounding box to a multiple of 2x4 if fit_horizontal_overhang
	normalize_bitmaps(font, fit_horizontal_overhang, horizontal_pixels_per_char, vertical_pixels_per_char)

	# Generate the FIGlet font file
	glyphs_count = generate_flf2(flfpath, font, comment, compressed, include_char_names, pixels_per_character, horizontal_pixels_per_char, vertical_pixels_per_char)

	print("Exported " + str(glyphs_count) + " characters to FLF2 file "+ flfpath +".")
	print()

	# Provide number of contained characters to caller
	return glyphs_count



############################################################################
#
# Example usage
#
# This should be all that needs modifying when using for another font
# Compression is usually very efficient for octants, and .flf can get quite
# large when a font has many glyphs, so it's typically False for testing and
# True for release.

#	# comment text block to be included in .flf file
#	with open("figlet_comment.txt", "r", encoding="utf-8", errors="replace") as f:
#		flf_comment = f.readlines()
#	# FIGlet missing character (tofu) glyph in BDF format
#	flf_missing_character = {
#		"bbx": (5, 8, 1, 0), "dwidth": 6,
#		"bitmap": [248, 136, 136, 136, 136, 136, 136, 248]
#	}
#	build_flf2("myfont.bdf", "myfont.flf", flf_comment, False, 8, True, flf_missing_character, False)
#   # Note the pixels_per_character can also use more descriptive names
#   # from the PixelsPerCharacter enum.
