#!/bin/python3

import os
import re
import sys
from pathlib import Path

from config import CHAR_HEIGHT
from unicode_blocks import unicode_path

OUTPUT_DIR = "glyphs"


def main():
    if len(sys.argv) != 2:
        print("Usage: bdf_to_txt.py [BFD input file]")
        exit(1)

    input_path = sys.argv[1]

    with open(input_path) as f:
        font_txt = f.read()
        chars_txt = (
            font_txt.split("ENDPROPERTIES")[1].split("ENDFONT")[0].strip()
        )

        chars_count = re.search(r"CHARS (\d+)\n", chars_txt)
        assert chars_count is not None

        chars_count = int(chars_count.group(1))
        chars = map(lambda txt: txt.strip(), chars_txt.split("STARTCHAR ")[1:])

        for char in chars:
            encoding_txt = re.search(r"ENCODING (\d+)\n", char)
            assert encoding_txt is not None

            encoding = int(encoding_txt.group(1))

            # Small check, ensure encoding and unicode are equal
            unicode_txt = re.search(r"^un?i?([0-9a-fA-F]+)\n", char)
            if unicode_txt is not None:
                unicode = int(unicode_txt.group(1), 16)

                assert encoding == unicode

            bitmap_txt = re.search(r"BITMAP\n((.|\n)*)\nENDCHAR", char)
            assert bitmap_txt is not None

            bitmap = bitmap_txt.group(1).split("\n")

            # Bounding box is given as
            #
            # BBX <WIDTH> <HEIGHT> <HORIZONTAL_OFFSET> <VERTICAL_OFFSET>
            #
            # However, the offset is computed from the left-hand bottom corner,
            # so we need to compute the real offset from the top of the glyph.
            bounding_box_txt = re.search(
                r"BBX (\d+) (\d+) (-?\d+) (-?\d+)", char
            )
            assert bounding_box_txt is not None

            box_width = int(bounding_box_txt.group(1))
            box_height = int(bounding_box_txt.group(2))
            box_offset = [
                int(bounding_box_txt.group(3)),
                CHAR_HEIGHT - box_height - int(bounding_box_txt.group(4)) - 3,
            ]

            path = Path(f"{OUTPUT_DIR}/{unicode_path(encoding)}")
            os.makedirs(path.parent, exist_ok=True)
            with open(path, "w") as f:
                # Offsets can be negative
                if box_offset[0] < 0 or box_offset[1] < 0:
                    f.write(
                        f"@offset={min(box_offset[0], 0)},{min(box_offset[1], 0)};"
                    )

                    if box_offset[0] < 0:
                        box_offset[0] = 0
                    if box_offset[1] < 0:
                        box_offset[1] = 0

                f.write("\n" * box_offset[1])
                for line_txt in bitmap:
                    f.write(" " * box_offset[0])
                    for c in [
                        line_txt[chunk : chunk + 2]
                        for chunk in range(0, len(line_txt), 2)
                    ]:
                        c = int(c, 16)
                        for i in range(0, 8):
                            if (c >> (7 - i)) & 1 == 1:
                                f.write("#")
                            else:
                                f.write(" ")

                    f.write("\n")


if __name__ == "__main__":
    main()
