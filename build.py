import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from pickle import BUILD
from shlex import quote
from shutil import rmtree
from typing import Optional, Sequence, cast
from tempfile import NamedTemporaryFile

import crayons  # type: ignore

from cozette_builder.changeloggen import get_changelog, get_last_ver
from cozette_builder.hidpi import double_size
from cozette_builder.imagegen import (
    add_margins,
    read_sample,
    save_charlist,
    save_sample,
)
from cozette_builder.scanner import (
    find_missing_codepoints,
    print_codepoints_for_changelog,
    scan_for_codepoints,
)

REPO_ROOT = Path(__file__).resolve().parent
BUILD_DIR = REPO_ROOT / "build"
FONTNAME = "Cozette"
SFDPATH = REPO_ROOT / "Cozette" / "Cozette.sfd"


@dataclass
class Generate:
    filename: str
    bitmap_fmt: Optional[str] = None

    def __str__(self):
        return (
            f'Generate("{self.filename}", "{self.bitmap_fmt}")'
            if self.bitmap_fmt
            else f'Generate("{self.filename}")'
        )


def save_images():
    print(crayons.yellow("Saving character map"))
    save_charlist(FONTNAME, SFDPATH, REPO_ROOT / "img")

    print(crayons.yellow("Saving sample image"))
    save_sample(
        FONTNAME,
        read_sample(REPO_ROOT / "img" / "sample.txt"),
        REPO_ROOT / "img" / "sample.png",
    )
    add_margins(REPO_ROOT / "img" / "sample.png")


def fontforge(open: Path, generate: Sequence[Generate]):
    BUILD_DIR.mkdir(exist_ok=True)
    script = "; ".join(
        [
            f'Open("{open}")',
            # 'RenameGlyphs("AGL with PUA")',
            # 'Reencode("unicode")',
        ]
        + [str(gen) for gen in generate]
    )
    # No idea why this doesn't work without shell=True
    subprocess.run(
        [f"fontforge -lang ff -c {quote(script)}"], cwd=BUILD_DIR, shell=True
    )


def rename_single(dir: Path, pattern: str, newname: str) -> Path:
    return cast(Path, next(dir.glob(pattern)).rename(dir / newname))


def gen_bitmap_formats(sfd_path: Path, prefix: str) -> Path:
    fontforge(
        open=sfd_path,
        generate=[
            Generate(f"{prefix}.", bitmap_fmt="bdf"),
        ],
    )
    bdf_path = rename_single(BUILD_DIR, f"{prefix}-*.bdf", f"{prefix}.bdf")
    fontforge(
        open=sfd_path,
        generate=[
            Generate(f"{prefix}.", "otb"),
            Generate(f"{prefix}.", "psf"),
            Generate(f"{prefix}.", "fnt"),
            Generate(f"{prefix}.dfont", "sbit"),
        ],
    )
    rename_single(BUILD_DIR, f"{prefix}-*.fnt", f"{prefix}.fnt")
    return bdf_path


def fix_ttf(ttfpath: Path, name: str):
    print(crayons.yellow(f"Generating TTF for {name}..."))
    version = "1.0"
    with SFDPATH.open() as f:
        for line in f.readlines():
            if line.startswith("Version "):
                version = line.split()[1]
                break
    with NamedTemporaryFile() as sfd:
        subprocess.run(
            [
                f"fontforge -c '"
                f'f = open("{ttfpath}"); '
                f"f.os2_version = 4; "
                f"f.os2_weight_width_slope_only = True; "
                f'f.save("{sfd.name}")\''
            ],
            cwd=BUILD_DIR,
            shell=True,
            check=True,
        )
        script = ";\n".join(
            [
                f'Open("{sfd.name}")',
                "SelectWorthOutputting()",
                "RemoveOverlap()",
                "CorrectDirection()",
                "ScaleToEm(2048)",
                'RenameGlyphs("AGL with PUA")',
                'Reencode("unicode")',
                f'SetTTFName(0x409, 3, "{name}")',
                f'SetTTFName(0x409, 5, "{version}")',
                f'SetTTFName(0x409, 8, "Ines <ines@moonwit.ch>")',
                f'SetTTFName(0x409, 9, "Ines <ines@moonwit.ch>")',
                f'SetTTFName(0x409, 11, "https://github.com/the-moonwitch/Cozette")',
                f'SetTTFName(0x409, 13, LoadStringFromFile({repr(str((REPO_ROOT / "LICENSE").resolve()))}))',
                'SetTTFName(0x409, 14, "https://github.com/the-moonwitch/Cozette/blob/master/LICENSE")',
                f'Generate("{name}.dfont")',
                f'Generate("{name}.otf")',
                f'Generate("{name}.ttf")',
                f'Generate("{name}.woff")',
                f'Generate("{name}.woff2")',
            ]
        )
        with NamedTemporaryFile(mode="w+", suffix=".pe") as f:
            print(f.name)
            f.write(script)
            f.flush()
            f.seek(0)
            subprocess.run(
                [f"fontforge -script {f.name}"],
                cwd=BUILD_DIR,
                shell=True,
                check=True,
            )
    # No idea why this doesn't work without shell=True
    ttfpath.unlink()


def make_hidpi(bdf_path: Path, out_path: Path):
    print(crayons.yellow("Generating hidpi font..."))
    with bdf_path.open() as i:
        with out_path.open("w") as o:
            double_size(i, o)
    print(crayons.green("Done!"))


BDF_CODEPOINT_RE = re.compile(r"BDFChar: \S+ (\d+)")


def variant(
    sfd_path: Path, variant_name: str, variant_source: Path
) -> tuple[Path, str]:
    outpath = BUILD_DIR / f"{variant_name}.sfd"
    replacements = {}
    with variant_source.open() as f:
        for line in f:
            if codepoint := BDF_CODEPOINT_RE.match(line):
                replacements[int(codepoint.group(1))] = next(f)

    with outpath.open("w") as f:
        with sfd_path.open() as src:
            replacement = None
            for line in src:
                if replacement is not None:
                    f.write(replacement)
                    replacement = None
                elif line.startswith("FAMILY_NAME"):
                    f.write(line)
                else:
                    f.write(line.replace("Cozette", variant_name))
                if codepoint := BDF_CODEPOINT_RE.match(line):
                    if int(codepoint.group(1)) in replacements:
                        replacement = replacements[int(codepoint.group(1))]

    return (outpath, variant_name)


def gen_versions(bdf_path: Path, font_name: str, filename_prefix: str):
    hidpi_path = BUILD_DIR / f"{filename_prefix}_hidpi.bdf"

    def bnp_invoc_ttf(name: str, format: str):
        return [
            REPO_ROOT / "bitsnpicas.sh",
            "convertbitmap",
            "-f",
            format,
            "-o",
            BUILD_DIR / f"{name}_tmp.{format}",
            "-s",
            "Cozette",
            "-r",
            name,
            "-T",
        ]

    subprocess.run(
        [
            BUILD_DIR.parent / "bitsnpicas.sh",
            "convertbitmap",
            "-f",
            "psf",
            "-o",
            BUILD_DIR / f"{filename_prefix}.psf",
            bdf_path,
        ],
        check=True,
    )
    subprocess.run(
        bnp_invoc_ttf(f"{font_name}Vector", "ttf") + [bdf_path], check=True
    )
    subprocess.run(
        bnp_invoc_ttf(f"{font_name}VectorBold", "ttf") + ["-b", bdf_path],
        check=True,
    )
    print(crayons.yellow("Fixing TTF variants..."))
    fix_ttf(BUILD_DIR / f"{font_name}Vector_tmp.ttf", f"{font_name}Vector")
    fix_ttf(
        BUILD_DIR / f"{font_name}VectorBold_tmp.ttf", f"{font_name}VectorBold"
    )
    print(crayons.green("Done!"))
    make_hidpi(bdf_path, hidpi_path)
    fontforge(
        open=hidpi_path,
        generate=[
            Generate(f"{hidpi_path.stem}.", "otb"),
            Generate(f"{hidpi_path.stem}.", "fnt"),
            Generate(f"{hidpi_path.stem}.dfont", "sbit"),
        ],
    )
    rename_single(BUILD_DIR, "*-26.fnt", f"{filename_prefix}_hidpi.fnt")
    subprocess.run(
        [
            BUILD_DIR.parent / "bitsnpicas.sh",
            "convertbitmap",
            "-f",
            "psf",
            "-o",
            hidpi_path.with_suffix(".psf"),
            hidpi_path,
        ],
        check=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action")
    images = subparsers.add_parser("images")
    changelog = subparsers.add_parser("changelog")
    fonts = subparsers.add_parser("fonts")
    scan = subparsers.add_parser("scan")
    # noinspection PyTypeChecker
    scan.add_argument("path", type=Path)  # type: ignore
    scan.add_argument("-s", "--print-source-files", action="store_true")
    scan.add_argument("-r", "--reverse", action="store_true")
    args = parser.parse_args()
    if args.action == "scan":
        missing_codepoints = find_missing_codepoints(
            SFDPATH,
            scan_for_codepoints(args.path),
        )
        if missing_codepoints:
            print_codepoints_for_changelog(
                missing_codepoints,
                print_source_files=args.print_source_files,
                reverse=args.reverse,
            )
        else:
            print(
                crayons.green(
                    f"All codepoints under {args.path} already "
                    f"supported by Cozette."
                )
            )
    if args.action == "images":
        print(crayons.blue("Saving sample images..."))
        save_images()
        print(crayons.green("Done!", bold=True))
    elif args.action == "fonts":
        rmtree(BUILD_DIR, ignore_errors=True)
        BUILD_DIR.mkdir(exist_ok=True)
        for sfd_path, font_name in (
            (SFDPATH, "Cozette"),
            variant(
                SFDPATH,
                "CozetteCrossedSeven",
                SFDPATH.parent / "variants" / "CozetteCrossedSeven.sfd",
            ),
        ):
            print(crayons.blue(f"Building bitmap formats for {font_name}..."))
            bdf_path = gen_bitmap_formats(sfd_path, font_name.lower())
            print(crayons.green("Done!", bold=True))
            print(crayons.blue(f"Building versions for {font_name}..."))
            gen_versions(bdf_path, font_name, font_name.lower())
        print(crayons.green("Done!", bold=True))
    elif args.action == "changelog":
        get_changelog()
    else:
        parser.print_usage()
