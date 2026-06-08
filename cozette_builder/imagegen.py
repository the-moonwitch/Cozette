import subprocess
import tempfile
from pathlib import Path
from shlex import quote
from typing import Dict, List, NamedTuple, Optional, Tuple
from unicodedata import east_asian_width as charwidth, category

from PIL import Image, ImageOps  # type: ignore

Color = Tuple[int, int, int]


def hex_to_rgb(color: str) -> Color:
    h = int(color, 16)
    return h >> 16, (h >> 8) & 0x00FF, h & 0x0000FF


Palette = Dict[str, Optional[Color]]


default_palette: Palette = dict(
    fg=hex_to_rgb("feffff"),
    bg=hex_to_rgb("2d2b33"),
    black=hex_to_rgb("383640"),
    red=hex_to_rgb("a09ebb"),
    green=hex_to_rgb("92b6b1"),
    yellow=hex_to_rgb("edaf97"),
    blue=hex_to_rgb("8789c0"),
    magenta=hex_to_rgb("e47b66"),
    cyan=hex_to_rgb("6b9080"),
    white=hex_to_rgb("969a97"),
    nc=None,
)


class Sample(NamedTuple):
    text: str
    width: int
    height: int


def wrap_text(src: str, width=79) -> Sample:
    sample_h = 1
    running_w = 0
    idx = 0
    linebreaks = []
    while idx < len(src):
        if running_w - int(src[idx] == " ") > width:
            linebreaks.append(idx - 1)
            running_w = 0
            sample_h += 1
        if any(
            (h := f"${color}$") == src[idx : len(h)]
            for color in default_palette.keys()
        ):
            idx += len(h)
        else:
            running_w += 1 if charwidth(src[idx]) not in "FW" else 2
            idx += 1
    for idx in reversed(linebreaks):
        src = src[:idx].rstrip() + "\n" + src[idx:].lstrip()
    return Sample(src, width, sample_h)


def read_sample(src_path: Path) -> Sample:
    with src_path.open() as f:
        src = f.read()
    stripped = src
    for color in default_palette.keys():
        stripped = stripped.replace(f"${color.upper()}$", "")
    lines = stripped.splitlines()
    h, w = len(lines), max(len(line) for line in lines)
    return Sample(src, w, h)


def save_sample(
    fnt: str,
    sample: Sample,
    output_path: Path,
    fgcolor: str = "#abb2bf",
    bgcolor: str = "#282c34",
    palette: Palette = None,
):
    if palette is None:
        palette = default_palette
    colored = color_text(sample.text, palette)
    with tempfile.NamedTemporaryFile("w", delete=False) as f:
        f.write(colored)
        fp = f.name
    cmd = quote(
        f"tput civis &&"
        f"cat {fp} && sleep 1 && "
        f"import -window $WINDOWID {output_path}"
    )
    subprocess.run(
        [
            "xterm",
            "-en",
            "utf8",
            "-fg",
            fgcolor,
            "-bg",
            bgcolor,
            "-fa",
            fnt,
            "-geometry",
            f"{sample.width}x{sample.height}+100+100",
            "-dc",
            "-cu",
            "-cn",
            "-e",
            f"bash -c {cmd}",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    Path(fp).unlink()


def color_escape_seq(color: Color = None):
    if color is None:
        return f"\033[38;0m"
    return f"\033[38;2;{color[0]};{color[1]};{color[2]}m"


def color_text(text: str, palette: Palette) -> str:
    colored_text = text
    for color in palette.keys():
        # The PyCharm MyPy plugin throws a fit at `palette.get(color)` because
        # it doesn't know that palette.get returns an Optional[Color], PyCharm
        # itself throws a fit here because of
        # https://youtrack.jetbrains.com/issue/PY-40439, and it sometimes
        # forgets that `palette` has a `.get` method, so ignore all those
        # warnings:
        # noinspection Mypy, PyTypedDict, PyUnresolvedReferences
        colored_text = colored_text.replace(
            f"${color.upper()}$", color_escape_seq(palette[color])
        )
    return colored_text


def make_charmap(sfd: Path) -> List[str]:
    text = [
        "        0 1 2 3 4 5 6 7 8 9 A B C D E F",
        "       ┌───────────────────────────────",
    ]
    codepoints = sfd_codepoints(sfd)
    for i in range(0, codepoints[-1] + 16, 16):
        line = ""
        for j in range(16):
            if (cp := i + j) in codepoints and not (
                category(chr(cp)).startswith(("Z", "Cc", "Cf"))
            ):
                ch = chr(cp)
            else:
                ch = " "
            # Workaround for combining characters
            if (0x300 <= cp < 0x370) and cp in codepoints:
                line += " "
            line += ch
            if charwidth(ch) not in "FW":
                line += " "
        if line := line.rstrip():
            text.append(f"U+{i//16:04X}_│{line}")
    return text


def sfd_codepoints(sfd: Path) -> List[int]:
    codepoints = []
    with sfd.open() as f:
        chars = False
        for line in f:
            if chars:
                if line.startswith("Encoding:"):
                    codepoints.append(int(line.split(maxsplit=2)[1]))
            elif line.startswith("BeginChars"):
                chars = True
    return sorted(codepoints)


def make_charlist_text(sfd: Path) -> str:
    text = ""
    for c in sfd_codepoints(sfd):
        if not (category(chr(c)).startswith(("Z", "Cc", "Cf"))):
            if 0x300 <= c < 0x370:
                text += f" {chr(c)} "
            else:
                ch = chr(c)
                text += ch if charwidth(ch) in "FWN" else f"{ch} "
        else:
            print("Skipping", c, category(chr(c)))
    return text


def stitch_charmap(files: List[Path], target: Path):
    images = [
        im.crop((0, 2, im.width, im.height - 2))
        for path in files
        if (im := Image.open(path).convert("RGB"))
    ]
    tot_height = sum(im.height for im in images)
    width = max(im.width for im in images)
    new_im = Image.new("RGB", (width, tot_height))
    y = 0
    for im in images:
        new_im.paste(im, (0, y))
        y += im.height
    for p in files:
        p.unlink()
    new_im.save(target)


def save_charlist(fnt: str, sfd: Path, output_dir: Path):
    text = make_charlist_text(sfd)
    sample = wrap_text(text)
    sample = Sample(text, sample.width + 1, sample.height)
    with (output_dir / "characters.txt").open("w") as f:
        f.write(text)
    save_sample(
        fnt,
        sample,
        output_dir / "characters.png",
        fgcolor="#24292e",
        bgcolor="#ffffff",
    )
    expand(output_dir / "characters.png", color="#ffffff")

    charmap = make_charmap(sfd)
    with (output_dir / "charmap.txt").open("w") as f:
        f.write(" ")
        f.write("\n ".join(charmap))
    files = []
    for chunk in range(0, len(charmap), 50):
        path = output_dir / f"charmap{chunk//50}_tmp.png"
        text = " \n".join(charmap[chunk : chunk + 50])
        save_sample(
            fnt,
            Sample(text, 41, len(charmap[chunk : chunk + 49])),
            path,
            fgcolor="#24292e",
            bgcolor="#ffffff",
        )
        files.append(path)
    stitch_charmap(files, output_dir / "charmap.png")
    expand(output_dir / "charmap.png", color="#ffffff")


def expand(sample_path: Path, margin: int = 40, color: str = "#282c34"):
    im: Image.Image = Image.open(sample_path).convert("RGB")
    im.load()
    new_im = ImageOps.expand(im, (margin, margin), fill=color)
    new_im.save(sample_path)


def add_margins(sample_path: Path, color: str = "#282c34"):
    im: Image.Image = Image.open(sample_path).convert("RGB")
    im.load()
    new_im = ImageOps.pad(
        im, (im.width * 2, im.height), method=Image.NEAREST, color=color
    )
    new_im.save(sample_path)
