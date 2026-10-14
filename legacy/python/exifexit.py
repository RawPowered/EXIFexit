#!/usr/bin/env python3
"""
EXIFexit — Shred EXIF, edit tags, inspect/rewrite PDF metadata, or scramble
identity to masquerade as any computer / mobile device worldwide.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import threading
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import piexif
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NullObject

from PIL import Image, UnidentifiedImageError

try:
    import fitz  # PyMuPDF — richer PDF file info + XMP wipe

    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

from locales import LANGUAGES, I18n
from masks import (
    CATEGORIES,
    REGION_LABELS,
    DeviceMask,
    ScrambleOptions,
    ScramblePayload,
    all_masks,
    build_scramble,
    filter_masks,
    mask_by_id,
    pick_random_mask,
    regions_present,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APP_NAME = "EXIFexit"
APP_VERSION = "1.3.0"
SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".jpe",
    ".jfif",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
    ".bmp",
    ".gif",
    ".ico",
}
# Formats where piexif can inject EXIF without re-encoding (lossless tag write)
PIEXIF_NATIVE_EXT = {".jpg", ".jpeg", ".jpe", ".jfif"}

# Tags that hold EXIF / orientation / GPS / etc. in Pillow Image.info
EXIF_INFO_KEYS = (
    "exif",
    "xmp",
    "icc_profile",
    "photoshop",
    "XML:com.adobe.xmp",
)

IFD_NAMES = ("0th", "Exif", "GPS", "Interop", "1st")

# Friendly catalog for the Studio quick-edit form and Add-tag combobox
COMMON_TAGS: list[tuple[str, int, str, str]] = [
    # (ifd, tag_id, name, value_hint)
    ("0th", piexif.ImageIFD.Make, "Make", "Camera manufacturer"),
    ("0th", piexif.ImageIFD.Model, "Model", "Camera model"),
    ("0th", piexif.ImageIFD.Software, "Software", "Software name"),
    ("0th", piexif.ImageIFD.Artist, "Artist", "Author / artist"),
    ("0th", piexif.ImageIFD.Copyright, "Copyright", "Copyright notice"),
    ("0th", piexif.ImageIFD.ImageDescription, "ImageDescription", "Caption / description"),
    ("0th", piexif.ImageIFD.DateTime, "DateTime", "YYYY:MM:DD HH:MM:SS"),
    ("0th", piexif.ImageIFD.Orientation, "Orientation", "1–8"),
    ("Exif", piexif.ExifIFD.DateTimeOriginal, "DateTimeOriginal", "YYYY:MM:DD HH:MM:SS"),
    ("Exif", piexif.ExifIFD.DateTimeDigitized, "DateTimeDigitized", "YYYY:MM:DD HH:MM:SS"),
    ("Exif", piexif.ExifIFD.LensMake, "LensMake", "Lens manufacturer"),
    ("Exif", piexif.ExifIFD.LensModel, "LensModel", "Lens model"),
    ("Exif", piexif.ExifIFD.FNumber, "FNumber", "e.g. 1.8 or 18/10"),
    ("Exif", piexif.ExifIFD.ExposureTime, "ExposureTime", "e.g. 1/125"),
    ("Exif", piexif.ExifIFD.ISOSpeedRatings, "ISOSpeedRatings", "e.g. 400"),
    ("Exif", piexif.ExifIFD.FocalLength, "FocalLength", "e.g. 50 or 50/1"),
    ("Exif", piexif.ExifIFD.UserComment, "UserComment", "Free-text comment"),
    ("GPS", piexif.GPSIFD.GPSLatitudeRef, "GPSLatitudeRef", "N or S"),
    ("GPS", piexif.GPSIFD.GPSLatitude, "GPSLatitude", "dd.dddd or dd,mm,ss"),
    ("GPS", piexif.GPSIFD.GPSLongitudeRef, "GPSLongitudeRef", "E or W"),
    ("GPS", piexif.GPSIFD.GPSLongitude, "GPSLongitude", "dd.dddd or dd,mm,ss"),
    ("GPS", piexif.GPSIFD.GPSAltitudeRef, "GPSAltitudeRef", "0=above / 1=below sea"),
    ("GPS", piexif.GPSIFD.GPSAltitude, "GPSAltitude", "meters, e.g. 150"),
]

# Standard PDF Info-dictionary keys (without leading slash)
PDF_STANDARD_KEYS = (
    "Title",
    "Author",
    "Subject",
    "Keywords",
    "Creator",
    "Producer",
    "CreationDate",
    "ModDate",
    "Trapped",
)
PDF_COMMON_KEYS = list(PDF_STANDARD_KEYS) + [
    "CustomField",
    "Company",
    "SourceModified",
]

# ---------------------------------------------------------------------------
# Core: EXIF stripping
# ---------------------------------------------------------------------------


@dataclass
class StripResult:
    source: Path
    output: Path | None = None
    success: bool = False
    message: str = ""
    tags_removed: list[str] = field(default_factory=list)
    had_metadata: bool = False


def is_supported_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS


def collect_images(paths: list[Path], recursive: bool = False) -> list[Path]:
    """Expand files and folders into a sorted list of supported images."""
    found: list[Path] = []
    seen: set[Path] = set()

    for path in paths:
        path = path.resolve()
        if path in seen:
            continue
        if path.is_file() and is_supported_image(path):
            seen.add(path)
            found.append(path)
        elif path.is_dir():
            iterator = path.rglob("*") if recursive else path.glob("*")
            for child in sorted(iterator):
                if child.is_file() and is_supported_image(child):
                    resolved = child.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        found.append(resolved)
    return found


def inspect_metadata(path: Path) -> list[str]:
    """Return a human-readable list of metadata present on the image."""
    tags: list[str] = []
    try:
        with Image.open(path) as img:
            if hasattr(img, "getexif"):
                exif = img.getexif()
                if exif:
                    tags.append(f"EXIF ({len(exif)} tags)")
                    try:
                        gps = exif.get_ifd(0x8825)
                        if gps:
                            tags.append(f"GPS ({len(gps)} tags)")
                    except Exception:
                        pass
            for key in EXIF_INFO_KEYS:
                if key in img.info and img.info[key]:
                    tags.append(key)
            for key in img.info:
                if key not in EXIF_INFO_KEYS and key not in tags:
                    if key.lower() in ("dpi", "jfif", "jfif_version", "jfif_unit", "jfif_density"):
                        continue
                    tags.append(str(key))
    except Exception as exc:
        tags.append(f"(could not inspect: {exc})")
    return tags


def strip_and_save(
    source: Path,
    output_dir: Path,
    *,
    suffix: str = "_clean",
    keep_icc: bool = False,
    overwrite: bool = False,
) -> StripResult:
    """Open an image, strip metadata, and write a clean copy to output_dir."""
    result = StripResult(source=source)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)

        stem = source.stem
        ext = source.suffix.lower()
        if ext in {".jpe", ".jfif"}:
            out_ext = ".jpg"
        else:
            out_ext = source.suffix

        out_name = f"{stem}{suffix}{out_ext}" if suffix else f"{stem}{out_ext}"
        out_path = output_dir / out_name

        if out_path.exists() and not overwrite:
            n = 1
            while out_path.exists():
                out_name = f"{stem}{suffix} ({n}){out_ext}" if suffix else f"{stem} ({n}){out_ext}"
                out_path = output_dir / out_name
                n += 1

        tags_before = inspect_metadata(source)
        result.tags_removed = tags_before
        result.had_metadata = bool(tags_before)

        with Image.open(source) as img:
            try:
                from PIL import ImageOps

                img = ImageOps.exif_transpose(img)
            except Exception:
                pass

            icc = img.info.get("icc_profile") if keep_icc else None

            mode = img.mode
            if mode in ("P", "PA"):
                img = img.convert("RGBA" if "A" in mode else "RGB")
                mode = img.mode

            clean = Image.new(mode, img.size)
            clean.putdata(list(img.getdata()))

            save_kwargs: dict = {}
            fmt = (img.format or "").upper()

            if out_ext.lower() in {".jpg", ".jpeg"}:
                if clean.mode not in ("RGB", "L"):
                    clean = clean.convert("RGB")
                save_kwargs.update(format="JPEG", quality=95, optimize=True)
            elif out_ext.lower() == ".png":
                save_kwargs.update(format="PNG", optimize=True)
            elif out_ext.lower() == ".webp":
                save_kwargs.update(format="WEBP", quality=95, method=6)
            elif out_ext.lower() in {".tif", ".tiff"}:
                save_kwargs.update(format="TIFF")
            elif out_ext.lower() == ".bmp":
                save_kwargs.update(format="BMP")
            elif out_ext.lower() == ".gif":
                save_kwargs.update(format="GIF")
            else:
                if fmt:
                    save_kwargs["format"] = fmt

            if icc:
                save_kwargs["icc_profile"] = icc

            clean.save(out_path, **save_kwargs)

        result.output = out_path
        result.success = True
        if result.had_metadata:
            result.message = f"Stripped {len(tags_before)} metadata field(s) → {out_path.name}"
        else:
            result.message = f"No metadata found; saved clean copy → {out_path.name}"
    except UnidentifiedImageError:
        result.message = "Not a recognized image file"
    except PermissionError:
        result.message = "Permission denied (file locked or read-only folder)"
    except OSError as exc:
        result.message = f"I/O error: {exc}"
    except Exception as exc:
        result.message = f"Error: {exc}"
        traceback.print_exc()
    return result


def batch_strip(
    sources: list[Path],
    output_dir: Path,
    *,
    suffix: str = "_clean",
    keep_icc: bool = False,
    overwrite: bool = False,
    on_progress: Callable[[int, int, StripResult], None] | None = None,
) -> list[StripResult]:
    results: list[StripResult] = []
    total = len(sources)
    for i, src in enumerate(sources, start=1):
        res = strip_and_save(
            src,
            output_dir,
            suffix=suffix,
            keep_icc=keep_icc,
            overwrite=overwrite,
        )
        results.append(res)
        if on_progress:
            on_progress(i, total, res)
    return results


# ---------------------------------------------------------------------------
# Core: EXIF Data Studio (read / edit / rewrite)
# ---------------------------------------------------------------------------


@dataclass
class ExifRow:
    """One editable EXIF tag row."""

    ifd: str
    tag_id: int
    name: str
    value_display: str
    raw_value: Any = None


@dataclass
class WriteResult:
    source: Path
    output: Path | None = None
    success: bool = False
    message: str = ""


def _tag_name(ifd: str, tag_id: int) -> str:
    try:
        return piexif.TAGS[ifd][tag_id]["name"]
    except Exception:
        return f"Tag{tag_id}"


def _value_to_display(value: Any) -> str:
    """Convert piexif raw values into editable text."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        # UserComment often has a charset header
        if value.startswith(b"ASCII\x00\x00\x00"):
            return value[8:].decode("ascii", errors="replace")
        if value.startswith(b"UNICODE\x00"):
            return value[8:].decode("utf-16", errors="replace")
        if value.startswith(b"\x00\x00\x00\x00\x00\x00\x00\x00"):
            return value[8:].decode("ascii", errors="replace")
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return value.decode("ascii", errors="replace")
            except Exception:
                return value.hex()
    if isinstance(value, tuple):
        # Single rational (num, den)
        if len(value) == 2 and all(isinstance(x, int) for x in value):
            num, den = value
            if den == 0:
                return f"{num}/{den}"
            if den == 1:
                return str(num)
            # Prefer 1/n exposure style when num==1
            if num == 1:
                return f"1/{den}"
            # Decimal when clean
            q = num / den
            if abs(q - round(q, 3)) < 1e-9:
                return f"{q:.3f}".rstrip("0").rstrip(".")
            return f"{num}/{den}"
        # Nested rationals e.g. GPS ((d,1),(m,1),(s,1))
        if all(isinstance(x, tuple) and len(x) == 2 for x in value):
            parts = []
            for num, den in value:
                if den == 1:
                    parts.append(str(num))
                else:
                    parts.append(f"{num}/{den}")
            return ", ".join(parts)
        # Simple int tuple e.g. GPSVersionID
        if all(isinstance(x, int) for x in value):
            return ", ".join(str(x) for x in value)
        return repr(value)
    return str(value)


def _parse_rational(text: str) -> tuple[int, int]:
    text = text.strip()
    if not text:
        raise ValueError("Empty rational")
    if "/" in text:
        a, b = text.split("/", 1)
        return int(a.strip()), int(b.strip())
    if "." in text or "e" in text.lower():
        # Convert float to rational with reasonable precision
        f = float(text)
        # Use 1000ths for decimals
        den = 1000
        num = int(round(f * den))
        # Reduce
        from math import gcd

        g = gcd(num, den) or 1
        return num // g, den // g
    return int(text), 1


def _parse_gps_coordinate(text: str) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    """
    Parse latitude/longitude into EXIF DMS rationals.
    Accepts:
      - decimal degrees: 30.25
      - DMS: 30, 15, 0  or  30/1, 15/1, 0/1
    """
    text = text.strip()
    if "," in text:
        parts = [p.strip() for p in text.split(",")]
        if len(parts) != 3:
            raise ValueError("GPS DMS needs 3 parts: degrees, minutes, seconds")
        return (
            _parse_rational(parts[0]),
            _parse_rational(parts[1]),
            _parse_rational(parts[2]),
        )
    # Decimal degrees → DMS
    dec = abs(float(text))
    degrees = int(dec)
    minutes_f = (dec - degrees) * 60
    minutes = int(minutes_f)
    seconds = (minutes_f - minutes) * 60
    # seconds as rational with 0.01 precision
    sec_num = int(round(seconds * 100))
    return (degrees, 1), (minutes, 1), (sec_num, 100)


def parse_exif_value(ifd: str, tag_id: int, text: str, previous: Any = None) -> Any:
    """
    Parse user-entered text into a piexif-compatible value.
    Uses previous type / tag type hints when available.
    """
    text = text.strip()
    type_name = ""
    try:
        type_name = piexif.TAGS[ifd][tag_id]["type"]
    except Exception:
        pass

    # GPS coordinate compounds
    if ifd == "GPS" and tag_id in (
        piexif.GPSIFD.GPSLatitude,
        piexif.GPSIFD.GPSLongitude,
    ):
        return _parse_gps_coordinate(text)

    if ifd == "GPS" and tag_id == piexif.GPSIFD.GPSAltitude:
        return _parse_rational(text)

    if ifd == "GPS" and tag_id == piexif.GPSIFD.GPSVersionID:
        parts = [int(p.strip()) for p in text.split(",")]
        return tuple(parts)

    if ifd == "GPS" and tag_id == piexif.GPSIFD.GPSAltitudeRef:
        return int(text)

    # Rational tags (common Exif)
    rational_tags = {
        ("Exif", piexif.ExifIFD.FNumber),
        ("Exif", piexif.ExifIFD.ExposureTime),
        ("Exif", piexif.ExifIFD.FocalLength),
        ("Exif", piexif.ExifIFD.ApertureValue),
        ("Exif", piexif.ExifIFD.MaxApertureValue),
        ("Exif", piexif.ExifIFD.ShutterSpeedValue),
        ("Exif", piexif.ExifIFD.BrightnessValue),
        ("Exif", piexif.ExifIFD.ExposureBiasValue),
        ("Exif", piexif.ExifIFD.FocalLengthIn35mmFilm),
    }
    if (ifd, tag_id) in rational_tags or type_name in ("RATIONAL", "SRATIONAL"):
        # ExposureTime often "1/125"
        return _parse_rational(text)

    # Integer tags
    int_tags = {
        ("Exif", piexif.ExifIFD.ISOSpeedRatings),
        ("0th", piexif.ImageIFD.Orientation),
        ("0th", piexif.ImageIFD.XResolution),
        ("0th", piexif.ImageIFD.YResolution),
    }
    if (ifd, tag_id) in int_tags or type_name in ("SHORT", "LONG", "BYTE", "SSHORT", "SLONG"):
        # X/YResolution are often rational in practice — if text has / treat as rational
        if "/" in text or "." in text:
            try:
                return _parse_rational(text)
            except Exception:
                pass
        if "," in text:
            return tuple(int(p.strip()) for p in text.split(","))
        return int(text)

    # UserComment needs charset header for many readers
    if ifd == "Exif" and tag_id == piexif.ExifIFD.UserComment:
        return b"ASCII\x00\x00\x00" + text.encode("ascii", errors="replace")

    # Default: ASCII bytes for strings; preserve previous non-string types if looks numeric
    if previous is not None:
        if isinstance(previous, int) and re.fullmatch(r"-?\d+", text):
            return int(text)
        if isinstance(previous, tuple):
            # try keep structure
            if all(isinstance(x, int) for x in previous):
                return tuple(int(p.strip()) for p in text.split(","))
            if len(previous) == 2 and all(isinstance(x, int) for x in previous):
                return _parse_rational(text)

    if type_name in ("ASCII",) or True:
        return text.encode("utf-8")


def load_exif_rows(path: Path) -> list[ExifRow]:
    """Load all EXIF tags from an image into editable rows."""
    rows: list[ExifRow] = []
    try:
        data = piexif.load(str(path))
    except Exception:
        # No EXIF or unsupported — empty studio still allows building tags
        return rows

    for ifd in IFD_NAMES:
        block = data.get(ifd) or {}
        if not isinstance(block, dict):
            continue
        for tag_id, value in sorted(block.items(), key=lambda kv: kv[0]):
            # Skip pointer tags piexif manages itself
            if ifd == "0th" and tag_id in (
                piexif.ImageIFD.ExifTag,
                piexif.ImageIFD.GPSTag,
            ):
                continue
            name = _tag_name(ifd, tag_id)
            rows.append(
                ExifRow(
                    ifd=ifd,
                    tag_id=int(tag_id),
                    name=name,
                    value_display=_value_to_display(value),
                    raw_value=value,
                )
            )
    return rows


def rows_to_exif_dict(rows: list[ExifRow]) -> dict:
    """Build a piexif dump-ready dict from edited rows."""
    data: dict[str, Any] = {ifd: {} for ifd in IFD_NAMES}
    data["thumbnail"] = None
    for row in rows:
        if row.ifd not in data:
            data[row.ifd] = {}
        try:
            value = parse_exif_value(row.ifd, row.tag_id, row.value_display, row.raw_value)
        except Exception:
            # Fall back to raw if parse fails and we still have it
            if row.raw_value is not None:
                value = row.raw_value
            else:
                value = row.value_display.encode("utf-8")
        data[row.ifd][row.tag_id] = value
    return data


def unique_output_path(
    output_dir: Path,
    source: Path,
    suffix: str,
    overwrite: bool,
    force_ext: str | None = None,
) -> Path:
    stem = source.stem
    ext = force_ext if force_ext is not None else source.suffix
    out_name = f"{stem}{suffix}{ext}" if suffix else f"{stem}{ext}"
    out_path = output_dir / out_name
    if out_path.exists() and not overwrite:
        n = 1
        while out_path.exists():
            out_name = f"{stem}{suffix} ({n}){ext}" if suffix else f"{stem} ({n}){ext}"
            out_path = output_dir / out_name
            n += 1
    return out_path


def write_exif_to_image(
    source: Path,
    output_dir: Path,
    rows: list[ExifRow],
    *,
    suffix: str = "_edited",
    overwrite: bool = False,
    overwrite_source: bool = False,
) -> WriteResult:
    """
    Write the given EXIF rows onto a copy of source (or onto the source itself).
    JPEG family uses piexif.insert for lossless metadata rewrite.
    Other formats re-save via Pillow with embedded EXIF where supported.
    """
    result = WriteResult(source=source)
    try:
        if not source.is_file():
            result.message = "Source file not found"
            return result

        exif_dict = rows_to_exif_dict(rows)
        try:
            exif_bytes = piexif.dump(exif_dict)
        except Exception as exc:
            result.message = f"Invalid EXIF data: {exc}"
            return result

        ext = source.suffix.lower()

        if overwrite_source:
            out_path = source
        else:
            output_dir.mkdir(parents=True, exist_ok=True)
            # Normalize jfif etc. to .jpg for output
            force_ext = ".jpg" if ext in {".jpe", ".jfif"} else None
            out_path = unique_output_path(
                output_dir, source, suffix, overwrite, force_ext=force_ext
            )

        if ext in PIEXIF_NATIVE_EXT:
            if out_path.resolve() != source.resolve():
                shutil.copy2(source, out_path)
            piexif.insert(exif_bytes, str(out_path))
        else:
            # Re-encode path for non-JPEG (best-effort)
            with Image.open(source) as img:
                save_kwargs: dict = {"exif": exif_bytes}
                out_ext = out_path.suffix.lower()
                work = img
                if out_ext in {".jpg", ".jpeg"} or ext in PIEXIF_NATIVE_EXT:
                    if work.mode not in ("RGB", "L"):
                        work = work.convert("RGB")
                    save_kwargs.update(format="JPEG", quality=95)
                elif out_ext in {".tif", ".tiff"}:
                    save_kwargs.update(format="TIFF")
                elif out_ext == ".webp":
                    save_kwargs.update(format="WEBP", quality=95)
                else:
                    # PNG and others — EXIF support is limited; still try
                    fmt = (img.format or "PNG").upper()
                    save_kwargs["format"] = fmt
                work.save(out_path, **save_kwargs)

        result.output = out_path
        result.success = True
        where = "source (in-place)" if overwrite_source else out_path.name
        result.message = f"Wrote {len(rows)} tag(s) → {where}"
    except Exception as exc:
        result.message = f"Error: {exc}"
        traceback.print_exc()
    return result


def apply_quick_fields_to_rows(
    rows: list[ExifRow],
    fields: dict[str, str],
) -> list[ExifRow]:
    """
    Merge quick-edit field values into the row list.
    fields keys are 'Make', 'Model', 'Artist', etc. Empty strings delete/skip.
    """
    # Map quick field name → (ifd, tag_id)
    mapping: dict[str, tuple[str, int]] = {
        "Make": ("0th", piexif.ImageIFD.Make),
        "Model": ("0th", piexif.ImageIFD.Model),
        "Software": ("0th", piexif.ImageIFD.Software),
        "Artist": ("0th", piexif.ImageIFD.Artist),
        "Copyright": ("0th", piexif.ImageIFD.Copyright),
        "ImageDescription": ("0th", piexif.ImageIFD.ImageDescription),
        "DateTime": ("0th", piexif.ImageIFD.DateTime),
        "DateTimeOriginal": ("Exif", piexif.ExifIFD.DateTimeOriginal),
        "DateTimeDigitized": ("Exif", piexif.ExifIFD.DateTimeDigitized),
        "LensModel": ("Exif", piexif.ExifIFD.LensModel),
        "FNumber": ("Exif", piexif.ExifIFD.FNumber),
        "ExposureTime": ("Exif", piexif.ExifIFD.ExposureTime),
        "ISOSpeedRatings": ("Exif", piexif.ExifIFD.ISOSpeedRatings),
        "FocalLength": ("Exif", piexif.ExifIFD.FocalLength),
        "UserComment": ("Exif", piexif.ExifIFD.UserComment),
        "GPSLatitudeRef": ("GPS", piexif.GPSIFD.GPSLatitudeRef),
        "GPSLatitude": ("GPS", piexif.GPSIFD.GPSLatitude),
        "GPSLongitudeRef": ("GPS", piexif.GPSIFD.GPSLongitudeRef),
        "GPSLongitude": ("GPS", piexif.GPSIFD.GPSLongitude),
        "GPSAltitudeRef": ("GPS", piexif.GPSIFD.GPSAltitudeRef),
        "GPSAltitude": ("GPS", piexif.GPSIFD.GPSAltitude),
    }

    index = {(r.ifd, r.tag_id): i for i, r in enumerate(rows)}
    new_rows = list(rows)

    for key, value in fields.items():
        if key not in mapping:
            continue
        ifd, tag_id = mapping[key]
        value = value.strip()
        if not value:
            # leave existing alone when blank
            continue
        name = _tag_name(ifd, tag_id)
        row = ExifRow(
            ifd=ifd,
            tag_id=tag_id,
            name=name,
            value_display=value,
            raw_value=None,
        )
        idx = index.get((ifd, tag_id))
        if idx is not None:
            new_rows[idx] = row
        else:
            new_rows.append(row)
            index[(ifd, tag_id)] = len(new_rows) - 1

    # Sensible GPS version when any GPS field is set
    gps_keys = ("GPSLatitude", "GPSLongitude", "GPSAltitude")
    if any(fields.get(k, "").strip() for k in gps_keys):
        ver_id = piexif.GPSIFD.GPSVersionID
        if ("GPS", ver_id) not in index:
            new_rows.append(
                ExifRow(
                    ifd="GPS",
                    tag_id=ver_id,
                    name="GPSVersionID",
                    value_display="2, 3, 0, 0",
                    raw_value=(2, 3, 0, 0),
                )
            )
        if fields.get("GPSLatitude", "").strip() and not fields.get("GPSLatitudeRef", "").strip():
            if ("GPS", piexif.GPSIFD.GPSLatitudeRef) not in {
                (r.ifd, r.tag_id) for r in new_rows
            }:
                new_rows.append(
                    ExifRow(
                        ifd="GPS",
                        tag_id=piexif.GPSIFD.GPSLatitudeRef,
                        name="GPSLatitudeRef",
                        value_display="N",
                    )
                )
        if fields.get("GPSLongitude", "").strip() and not fields.get("GPSLongitudeRef", "").strip():
            if ("GPS", piexif.GPSIFD.GPSLongitudeRef) not in {
                (r.ifd, r.tag_id) for r in new_rows
            }:
                new_rows.append(
                    ExifRow(
                        ifd="GPS",
                        tag_id=piexif.GPSIFD.GPSLongitudeRef,
                        name="GPSLongitudeRef",
                        value_display="W",
                    )
                )

    return new_rows


def rows_to_quick_field_values(rows: list[ExifRow]) -> dict[str, str]:
    """Extract common field values from rows for the quick-edit form."""
    wanted = {
        "Make",
        "Model",
        "Software",
        "Artist",
        "Copyright",
        "ImageDescription",
        "DateTime",
        "DateTimeOriginal",
        "DateTimeDigitized",
        "LensModel",
        "FNumber",
        "ExposureTime",
        "ISOSpeedRatings",
        "FocalLength",
        "UserComment",
        "GPSLatitudeRef",
        "GPSLatitude",
        "GPSLongitudeRef",
        "GPSLongitude",
        "GPSAltitudeRef",
        "GPSAltitude",
    }
    out = {k: "" for k in wanted}
    for r in rows:
        if r.name in out:
            out[r.name] = r.value_display
    return out


# ---------------------------------------------------------------------------
# Core: PDF metadata / file data
# ---------------------------------------------------------------------------


@dataclass
class PdfMetaRow:
    """One editable PDF document-info (or custom) metadata field."""

    key: str  # without leading slash, e.g. Title
    value: str
    group: str = "Document"  # Document | Custom | XMP
    editable: bool = True


def _pdf_key_name(raw: str) -> str:
    return raw[1:] if raw.startswith("/") else raw


def _pdf_slash_key(key: str) -> str:
    key = key.strip()
    if not key:
        return key
    return key if key.startswith("/") else f"/{key}"


def _format_ts(ts: float | None) -> str:
    if ts is None:
        return ""
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, OverflowError, ValueError):
        return str(ts)


def _pdf_value_str(value: Any) -> str:
    if value is None or isinstance(value, NullObject):
        return ""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.decode("latin-1", errors="replace")
    text = str(value)
    # pypdf sometimes returns "Null"
    if text in ("Null", "None"):
        return ""
    return text


def normalize_pdf_date(text: str) -> str:
    """
    Accept PDF D:… dates or common human forms and return a PDF date string.
    Leaves already-valid D: strings alone; empty stays empty.
    """
    text = text.strip()
    if not text:
        return ""
    if text.startswith("D:"):
        return text
    # Try several human formats
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y:%m:%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y",
    ):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.strftime("D:%Y%m%d%H%M%S")
        except ValueError:
            continue
    # Pass through (user may know the PDF format)
    return text


def load_pdf_file_info(path: Path) -> list[tuple[str, str]]:
    """
    Return ordered (label, value) pairs describing file + PDF structure data.
    Read-only in the UI.
    """
    path = path.resolve()
    rows: list[tuple[str, str]] = []
    st = path.stat()
    rows.append(("Path", str(path)))
    rows.append(("Filename", path.name))
    rows.append(("Extension", path.suffix.lower() or "(none)"))
    rows.append(("Size (bytes)", str(st.st_size)))
    rows.append(("Size", _human_size(st.st_size)))
    rows.append(("Created (filesystem)", _format_ts(getattr(st, "st_ctime", None))))
    rows.append(("Modified (filesystem)", _format_ts(getattr(st, "st_mtime", None))))
    rows.append(("Accessed (filesystem)", _format_ts(getattr(st, "st_atime", None))))

    # pypdf structural info
    try:
        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                pass
        rows.append(("Encrypted", "Yes" if reader.is_encrypted else "No"))
        rows.append(("Page count", str(len(reader.pages))))
        if reader.pdf_header:
            rows.append(("PDF header", reader.pdf_header.strip()))
        # Page size of first page
        if reader.pages:
            try:
                box = reader.pages[0].mediabox
                w, h = float(box.width), float(box.height)
                rows.append(("Page 1 size (pts)", f"{w:.1f} × {h:.1f}"))
                rows.append(("Page 1 size (in)", f"{w / 72:.2f} × {h / 72:.2f}"))
            except Exception:
                pass
        # Outline / form presence
        try:
            outlines = reader.outline
            rows.append(("Bookmarks", "Yes" if outlines else "No"))
        except Exception:
            rows.append(("Bookmarks", "?"))
        try:
            has_form = bool(getattr(reader, "get_fields", lambda: None)())
            rows.append(("AcroForm fields", "Yes" if has_form else "No"))
        except Exception:
            pass
        # XMP presence
        try:
            xmp = reader.xmp_metadata
            rows.append(("XMP packet", "Present" if xmp is not None else "None"))
        except Exception:
            rows.append(("XMP packet", "?"))
    except Exception as exc:
        rows.append(("PDF parse (pypdf)", f"Error: {exc}"))

    # PyMuPDF extras
    if HAS_FITZ:
        try:
            doc = fitz.open(str(path))
            meta = doc.metadata or {}
            rows.append(("PDF version (engine)", meta.get("format") or ""))
            if meta.get("encryption"):
                rows.append(("Encryption detail", str(meta.get("encryption"))))
            rows.append(("Page count (engine)", str(doc.page_count)))
            try:
                xml = doc.get_xml_metadata() or ""
                rows.append(("XMP length (chars)", str(len(xml)) if xml else "0"))
            except Exception:
                pass
            perms = []
            try:
                # permissions bitmask when encrypted
                if doc.is_encrypted:
                    perms.append(f"encrypted={doc.is_encrypted}")
                    perms.append(f"needs_pass={doc.needs_pass}")
            except Exception:
                pass
            if perms:
                rows.append(("Permissions", ", ".join(perms)))
            doc.close()
        except Exception as exc:
            rows.append(("PDF parse (PyMuPDF)", f"Error: {exc}"))

    return rows


def _human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


def load_pdf_metadata_rows(path: Path) -> list[PdfMetaRow]:
    """Load document Info dictionary (+ light XMP summary) into editable rows."""
    rows: list[PdfMetaRow] = []
    seen: set[str] = set()

    try:
        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                pass
        meta = reader.metadata
        if meta:
            for raw_key in meta.keys():
                key = _pdf_key_name(str(raw_key))
                value = _pdf_value_str(meta.get(raw_key))
                if not value and value != "0":
                    # keep empty standard keys visible? skip empties for noise
                    if key not in PDF_STANDARD_KEYS:
                        continue
                group = "Document" if key in PDF_STANDARD_KEYS else "Custom"
                rows.append(PdfMetaRow(key=key, value=value, group=group, editable=True))
                seen.add(key.lower())
    except Exception:
        pass

    # Ensure standard keys exist in the table for easy editing (blank if missing)
    for key in PDF_STANDARD_KEYS:
        if key.lower() not in seen:
            rows.append(PdfMetaRow(key=key, value="", group="Document", editable=True))
            seen.add(key.lower())

    # XMP summary (observe-only as a single row if present)
    xmp_preview = ""
    if HAS_FITZ:
        try:
            doc = fitz.open(str(path))
            xml = doc.get_xml_metadata() or ""
            doc.close()
            if xml.strip():
                # Compact preview
                compact = re.sub(r"\s+", " ", xml).strip()
                xmp_preview = compact[:500] + ("…" if len(compact) > 500 else "")
        except Exception:
            pass
    if not xmp_preview:
        try:
            reader = PdfReader(str(path), strict=False)
            xmp = reader.xmp_metadata
            if xmp is not None:
                xmp_preview = "(XMP present — structured packet; clear via Shred XMP)"
        except Exception:
            pass
    if xmp_preview:
        rows.append(
            PdfMetaRow(
                key="XMP_Preview",
                value=xmp_preview,
                group="XMP",
                editable=False,
            )
        )

    # Sort: Document standards first, then custom, then XMP
    group_order = {"Document": 0, "Custom": 1, "XMP": 2}
    std_order = {k: i for i, k in enumerate(PDF_STANDARD_KEYS)}
    rows.sort(
        key=lambda r: (
            group_order.get(r.group, 9),
            std_order.get(r.key, 100),
            r.key.lower(),
        )
    )
    return rows


def pdf_rows_to_metadata_dict(rows: list[PdfMetaRow], *, include_empty: bool = False) -> dict[str, str]:
    """Convert UI rows into pypdf add_metadata dict (keys with leading /)."""
    out: dict[str, str] = {}
    for row in rows:
        if not row.editable:
            continue
        if row.group == "XMP":
            continue
        key = row.key.strip()
        if not key or key == "XMP_Preview":
            continue
        value = row.value
        if key in ("CreationDate", "ModDate"):
            value = normalize_pdf_date(value)
        if not value and not include_empty:
            continue
        out[_pdf_slash_key(key)] = value
    return out


def write_pdf_metadata(
    source: Path,
    output_dir: Path,
    rows: list[PdfMetaRow],
    *,
    suffix: str = "_meta",
    overwrite: bool = False,
    overwrite_source: bool = False,
    strip_all: bool = False,
    strip_xmp: bool = False,
) -> WriteResult:
    """
    Write document metadata onto a copy of the PDF (or in-place).
    strip_all: clear document info fields (empty strings / wipe).
    strip_xmp: remove XMP packet when PyMuPDF is available.
    """
    result = WriteResult(source=source)
    try:
        if not source.is_file():
            result.message = "Source PDF not found"
            return result
        if source.suffix.lower() != ".pdf":
            result.message = "Not a PDF file"
            return result

        if overwrite_source:
            out_path = source
            # Write via temp then replace for safety
            tmp_path = source.with_suffix(source.suffix + ".exifexit.tmp")
        else:
            output_dir.mkdir(parents=True, exist_ok=True)
            out_path = unique_output_path(output_dir, source, suffix, overwrite, force_ext=".pdf")
            tmp_path = out_path

        reader = PdfReader(str(source), strict=False)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                result.message = "PDF is encrypted and could not be opened with an empty password"
                return result

        writer = PdfWriter()
        writer.append(reader)

        if strip_all:
            # Wipe known info keys by setting empty; pypdf keeps producer otherwise
            empty = { _pdf_slash_key(k): "" for k in PDF_STANDARD_KEYS }
            writer.add_metadata(empty)
            # Also clear any custom keys we saw in rows
            for row in rows:
                if row.editable and row.key and row.key != "XMP_Preview":
                    writer.add_metadata({_pdf_slash_key(row.key): ""})
        else:
            meta = pdf_rows_to_metadata_dict(rows, include_empty=True)
            # Always write full set from table (empty string clears a field)
            if meta:
                writer.add_metadata(meta)

        # Write PDF bytes first
        with open(tmp_path, "wb") as fh:
            writer.write(fh)

        # Optional XMP strip / polish with PyMuPDF
        if strip_xmp or strip_all:
            if HAS_FITZ:
                try:
                    doc = fitz.open(str(tmp_path))
                    try:
                        doc.del_xml_metadata()
                    except Exception:
                        pass
                    if strip_all:
                        doc.set_metadata(
                            {
                                "title": "",
                                "author": "",
                                "subject": "",
                                "keywords": "",
                                "creator": "",
                                "producer": "",
                                "creationDate": "",
                                "modDate": "",
                                "trapped": "",
                            }
                        )
                    polished = str(tmp_path) + ".fitz.pdf"
                    doc.save(polished, garbage=4, deflate=True, clean=True)
                    doc.close()
                    os.replace(polished, tmp_path)
                except Exception:
                    traceback.print_exc()
            elif strip_xmp:
                # Note only — still succeeded for Info dict
                pass

        if overwrite_source and tmp_path != out_path:
            os.replace(tmp_path, out_path)

        result.output = out_path
        result.success = True
        if strip_all:
            result.message = f"Shredded PDF metadata → {out_path.name}"
        else:
            written = len(pdf_rows_to_metadata_dict(rows, include_empty=False))
            result.message = f"Wrote {written} PDF field(s) → {out_path.name}"
    except Exception as exc:
        result.message = f"Error: {exc}"
        traceback.print_exc()
        # cleanup temp
        try:
            if "tmp_path" in locals() and tmp_path.exists() and overwrite_source:
                tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
    return result


def apply_pdf_quick_fields(rows: list[PdfMetaRow], fields: dict[str, str]) -> list[PdfMetaRow]:
    """Merge quick-edit values into PDF metadata rows (blank = leave alone)."""
    index = {r.key.lower(): i for i, r in enumerate(rows) if r.editable}
    new_rows = list(rows)
    for key, value in fields.items():
        value = value.strip()
        if not value and value != "0":
            # allow explicit clear only if key present in fields with special? skip blank
            continue
        if key in ("CreationDate", "ModDate"):
            value = normalize_pdf_date(value)
        group = "Document" if key in PDF_STANDARD_KEYS else "Custom"
        row = PdfMetaRow(key=key, value=value, group=group, editable=True)
        idx = index.get(key.lower())
        if idx is not None:
            new_rows[idx] = row
        else:
            new_rows.append(row)
            index[key.lower()] = len(new_rows) - 1
    return new_rows


def pdf_rows_to_quick_values(rows: list[PdfMetaRow]) -> dict[str, str]:
    wanted = list(PDF_STANDARD_KEYS)
    out = {k: "" for k in wanted}
    for r in rows:
        if r.key in out:
            out[r.key] = r.value
    return out


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------


class EXIFexitApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME}  v{APP_VERSION}")
        self.minsize(960, 700)
        self.geometry("1040x780")

        self.i18n = I18n("en")
        self._lang_code = tk.StringVar(value="en")
        self._lang_display = tk.StringVar(value=LANGUAGES["en"])
        # Maps widget → (method, i18n_key or callable)
        self._i18n_widgets: list[tuple[Any, str, str]] = []

        # Shared / shred state
        self.file_list: list[Path] = []
        self.output_dir = tk.StringVar(value=str(Path.home() / "Pictures" / "EXIFexit"))
        self.suffix_var = tk.StringVar(value="_clean")
        self.keep_icc_var = tk.BooleanVar(value=False)
        self.overwrite_var = tk.BooleanVar(value=False)
        self.recursive_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value=self.i18n("status_add_images"))
        self.progress_var = tk.DoubleVar(value=0.0)
        self._busy = False

        # Studio state
        self.studio_path: Path | None = None
        self.studio_rows: list[ExifRow] = []
        self.studio_output_dir = tk.StringVar(value=str(Path.home() / "Pictures" / "EXIFexit"))
        self.studio_suffix = tk.StringVar(value="_edited")
        self.studio_overwrite = tk.BooleanVar(value=False)
        self.studio_inplace = tk.BooleanVar(value=False)
        self.studio_file_label = tk.StringVar(value=self.i18n("no_image_loaded"))
        self.studio_status = tk.StringVar(value=self.i18n("status_studio"))
        self._quick_vars: dict[str, tk.StringVar] = {}

        # PDF Studio state
        self.pdf_path: Path | None = None
        self.pdf_rows: list[PdfMetaRow] = []
        self.pdf_file_info: list[tuple[str, str]] = []
        self.pdf_output_dir = tk.StringVar(value=str(Path.home() / "Documents" / "EXIFexit"))
        self.pdf_suffix = tk.StringVar(value="_meta")
        self.pdf_overwrite = tk.BooleanVar(value=False)
        self.pdf_inplace = tk.BooleanVar(value=False)
        self.pdf_strip_xmp = tk.BooleanVar(value=True)
        self.pdf_file_label = tk.StringVar(value=self.i18n("no_pdf_loaded"))
        self.pdf_status = tk.StringVar(value=self.i18n("status_pdf"))
        self._pdf_quick_vars: dict[str, tk.StringVar] = {}

        # Scramble / mask state
        self.scramble_category = tk.StringVar(value="all")
        self.scramble_region = tk.StringVar(value="all")
        self.scramble_mask_id = tk.StringVar(value="")
        self.scramble_opt_gps = tk.BooleanVar(value=True)
        self.scramble_opt_dt = tk.BooleanVar(value=True)
        self.scramble_opt_exp = tk.BooleanVar(value=True)
        self.scramble_opt_artist = tk.BooleanVar(value=False)
        self.scramble_artist = tk.StringVar(value="")
        self.scramble_comment = tk.StringVar(value="")
        self.scramble_pdf_title = tk.StringVar(value="")
        self.scramble_pdf_author = tk.StringVar(value="")
        self.scramble_pdf_subject = tk.StringVar(value="")
        self.scramble_pdf_keywords = tk.StringVar(value="")
        self.scramble_batch_suffix = tk.StringVar(value="_masked")
        self.scramble_status = tk.StringVar(value=self.i18n("status_scramble"))
        self.scramble_mask_count = tk.StringVar(value="")
        self._last_payload: ScramblePayload | None = None
        self._mask_id_by_label: dict[str, str] = {}

        self._apply_theme()
        self._build_ui()
        self._center_window()
        self._refresh_mask_filters()
        self._set_language("en")

    # -- Theme ---------------------------------------------------------------

    def _apply_theme(self) -> None:
        self.configure(bg="#1e1e2e")
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        bg = "#1e1e2e"
        surface = "#2a2a3c"
        surface2 = "#34344a"
        fg = "#e8e8f0"
        muted = "#a0a0b8"
        accent = "#7c6af7"
        accent_hover = "#9486ff"
        danger = "#e85d75"
        success = "#5dcea3"

        style.configure(".", background=bg, foreground=fg, fieldbackground=surface, borderwidth=0)
        style.configure("TFrame", background=bg)
        style.configure("Surface.TFrame", background=surface)
        style.configure("TLabel", background=bg, foreground=fg, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=bg, foreground=muted, font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=bg, foreground=fg, font=("Segoe UI Semibold", 16))
        style.configure("Subtitle.TLabel", background=bg, foreground=muted, font=("Segoe UI", 9))
        style.configure("Surface.TLabel", background=surface, foreground=fg)
        style.configure("Status.TLabel", background=surface, foreground=muted, font=("Segoe UI", 9))
        style.configure("TNotebook", background=bg, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=surface2,
            foreground=muted,
            font=("Segoe UI Semibold", 10),
            padding=(16, 8),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", accent)],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "TCombobox",
            fieldbackground=surface,
            background=surface2,
            foreground=fg,
            arrowcolor=fg,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", surface)],
            foreground=[("readonly", fg)],
        )
        style.configure(
            "TButton",
            background=surface2,
            foreground=fg,
            font=("Segoe UI", 10),
            padding=(12, 6),
            borderwidth=0,
            focuscolor=accent,
        )
        style.map(
            "TButton",
            background=[("active", accent), ("disabled", surface)],
            foreground=[("disabled", muted)],
        )
        style.configure(
            "Accent.TButton",
            background=accent,
            foreground="#ffffff",
            font=("Segoe UI Semibold", 10),
            padding=(16, 8),
        )
        style.map(
            "Accent.TButton",
            background=[("active", accent_hover), ("disabled", surface2)],
            foreground=[("disabled", muted)],
        )
        style.configure(
            "Danger.TButton",
            background=surface2,
            foreground=danger,
            font=("Segoe UI", 10),
            padding=(12, 6),
        )
        style.map("Danger.TButton", background=[("active", "#4a2a32")])
        style.configure(
            "TEntry",
            fieldbackground=surface,
            foreground=fg,
            insertcolor=fg,
            padding=6,
        )
        style.configure(
            "TCheckbutton",
            background=bg,
            foreground=fg,
            font=("Segoe UI", 10),
            focuscolor=bg,
        )
        style.map("TCheckbutton", background=[("active", bg)])
        style.configure(
            "TLabelframe",
            background=bg,
            foreground=fg,
        )
        style.configure(
            "TLabelframe.Label",
            background=bg,
            foreground=muted,
            font=("Segoe UI Semibold", 9),
        )
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor=surface,
            background=success,
            borderwidth=0,
            thickness=8,
        )
        style.configure(
            "Treeview",
            background=surface,
            foreground=fg,
            fieldbackground=surface,
            font=("Segoe UI", 9),
            rowheight=26,
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading",
            background=surface2,
            foreground=fg,
            font=("Segoe UI Semibold", 9),
            borderwidth=0,
            relief="flat",
        )
        style.map(
            "Treeview",
            background=[("selected", accent)],
            foreground=[("selected", "#ffffff")],
        )
        style.configure("TSeparator", background=surface2)

        self._colors = {
            "bg": bg,
            "surface": surface,
            "surface2": surface2,
            "fg": fg,
            "muted": muted,
            "accent": accent,
            "success": success,
            "danger": danger,
            "warn": "#e8c547",
        }

    def _center_window(self) -> None:
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = max(0, (sw - w) // 2), max(0, (sh - h) // 3)
        self.geometry(f"+{x}+{y}")

    # -- Layout --------------------------------------------------------------

    # -- i18n helpers --------------------------------------------------------

    def t(self, key: str, **kwargs: object) -> str:
        return self.i18n.t(key, **kwargs)

    def _reg(self, widget: Any, attr: str, key: str) -> Any:
        """Register a widget attribute for live re-translation."""
        self._i18n_widgets.append((widget, attr, key))
        try:
            widget[attr] = self.t(key)
        except Exception:
            pass
        return widget

    def _set_language(self, lang: str) -> None:
        if lang not in LANGUAGES:
            lang = "en"
        self.i18n.set_language(lang)
        self._lang_code.set(lang)
        self._lang_display.set(LANGUAGES[lang])
        self.title(f"{APP_NAME}  v{APP_VERSION}")

        for widget, attr, key in self._i18n_widgets:
            try:
                widget[attr] = self.t(key)
            except Exception:
                pass

        # Notebook tabs
        try:
            self.notebook.tab(self.shred_tab, text=self.t("tab_shred"))
            self.notebook.tab(self.studio_tab, text=self.t("tab_studio"))
            self.notebook.tab(self.pdf_tab, text=self.t("tab_pdf"))
            self.notebook.tab(self.scramble_tab, text=self.t("tab_scramble"))
        except Exception:
            pass

        if hasattr(self, "subtitle_label"):
            self.subtitle_label.configure(text=self.t("app_subtitle"))

        # Tree headings that were static
        try:
            self.studio_tree.heading("ifd", text=self.t("heading_ifd"))
            self.studio_tree.heading("id", text=self.t("heading_id"))
            self.studio_tree.heading("name", text=self.t("heading_tag"))
            self.studio_tree.heading("value", text=self.t("heading_value"))
        except Exception:
            pass
        try:
            self.pdf_meta_tree.heading("group", text=self.t("heading_group"))
            self.pdf_meta_tree.heading("key", text=self.t("heading_key"))
            self.pdf_meta_tree.heading("value", text=self.t("heading_value"))
        except Exception:
            pass

        # Default status strings when idle-ish
        if not self.studio_path:
            self.studio_file_label.set(self.t("no_image_loaded"))
            self.studio_status.set(self.t("status_studio"))
        if not self.pdf_path:
            self.pdf_file_label.set(self.t("no_pdf_loaded"))
            self.pdf_status.set(self.t("status_pdf"))
        if self._last_payload is None:
            self.scramble_status.set(self.t("status_scramble"))

        self._refresh_mask_filters(keep_selection=True)
        self._update_category_labels()

    def _on_language_picked(self, _event: Any = None) -> None:
        display = self._lang_display.get()
        for code, name in LANGUAGES.items():
            if name == display:
                self._set_language(code)
                return

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, style="TFrame")
        outer.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(outer)
        header.pack(fill=tk.X, padx=16, pady=(12, 4))

        left_h = ttk.Frame(header)
        left_h.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(left_h, text="EXIFexit", style="Title.TLabel").pack(anchor=tk.W)
        self.subtitle_label = ttk.Label(
            left_h,
            text=self.t("app_subtitle"),
            style="Subtitle.TLabel",
        )
        self.subtitle_label.pack(anchor=tk.W)

        lang_box = ttk.Frame(header)
        lang_box.pack(side=tk.RIGHT, anchor=tk.N)
        self._lang_label = ttk.Label(lang_box, text=self.t("language"), style="Muted.TLabel")
        self._lang_label.pack(anchor=tk.E)
        self._reg(self._lang_label, "text", "language")
        self.lang_combo = ttk.Combobox(
            lang_box,
            textvariable=self._lang_display,
            values=list(LANGUAGES.values()),
            state="readonly",
            width=28,
        )
        self.lang_combo.pack(anchor=tk.E, pady=(2, 0))
        self.lang_combo.bind("<<ComboboxSelected>>", self._on_language_picked)

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 0))

        self.shred_tab = ttk.Frame(self.notebook)
        self.studio_tab = ttk.Frame(self.notebook)
        self.pdf_tab = ttk.Frame(self.notebook)
        self.scramble_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.shred_tab, text=self.t("tab_shred"))
        self.notebook.add(self.studio_tab, text=self.t("tab_studio"))
        self.notebook.add(self.pdf_tab, text=self.t("tab_pdf"))
        self.notebook.add(self.scramble_tab, text=self.t("tab_scramble"))

        self._build_shred_tab(self.shred_tab)
        self._build_studio_tab(self.studio_tab)
        self._build_pdf_tab(self.pdf_tab)
        self._build_scramble_tab(self.scramble_tab)

        status = ttk.Frame(outer, style="Surface.TFrame")
        status.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Label(status, textvariable=self.status_var, style="Status.TLabel").pack(
            anchor=tk.W, padx=12, pady=6
        )

        self.bind("<Control-o>", lambda e: self._shortcut_open())
        self.bind("<Control-O>", lambda e: self._shortcut_open())
        self.bind("<Delete>", lambda e: self._shortcut_delete())
        self.bind("<Control-Return>", lambda e: self._shortcut_action())
        self.bind("<Control-v>", self._paste_paths)

    def _current_tab_name(self) -> str:
        try:
            idx = self.notebook.index(self.notebook.select())
        except tk.TclError:
            return "shred"
        tabs = ("shred", "studio", "pdf", "scramble")
        return tabs[idx] if 0 <= idx < len(tabs) else "shred"

    def _shortcut_open(self) -> None:
        tab = self._current_tab_name()
        if tab == "studio":
            self._studio_open()
        elif tab == "pdf":
            self._pdf_open()
        elif tab == "scramble":
            self._scramble_random()
        else:
            self._add_files()

    def _shortcut_delete(self) -> None:
        tab = self._current_tab_name()
        if tab == "studio":
            self._studio_delete_tag()
        elif tab == "pdf":
            self._pdf_delete_field()
        else:
            self._remove_selected()

    def _shortcut_action(self) -> None:
        tab = self._current_tab_name()
        if tab == "studio":
            self._studio_write()
        elif tab == "pdf":
            self._pdf_write()
        elif tab == "scramble":
            self._scramble_preview()
        else:
            self._start_shred()

    # -- Shred tab -----------------------------------------------------------

    def _build_shred_tab(self, root: ttk.Frame) -> None:
        tools = ttk.Frame(root)
        tools.pack(fill=tk.X, padx=12, pady=(10, 0))
        self._reg(ttk.Button(tools, command=self._add_files), "text", "add_images").pack(
            side=tk.LEFT, padx=(0, 6)
        )
        self._reg(ttk.Button(tools, command=self._add_folder), "text", "add_folder").pack(
            side=tk.LEFT, padx=(0, 6)
        )
        self._reg(ttk.Button(tools, command=self._remove_selected), "text", "remove").pack(
            side=tk.LEFT, padx=(0, 6)
        )
        self._reg(
            ttk.Button(tools, style="Danger.TButton", command=self._clear_all),
            "text",
            "clear_list",
        ).pack(side=tk.LEFT, padx=(0, 6))
        self._reg(
            ttk.Button(tools, command=self._open_selected_in_studio), "text", "open_in_studio"
        ).pack(side=tk.LEFT, padx=(0, 6))
        self._reg(
            ttk.Checkbutton(tools, variable=self.recursive_var),
            "text",
            "recursive",
        ).pack(side=tk.RIGHT)

        list_frame = ttk.Frame(root, style="Surface.TFrame")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        columns = ("name", "size", "metadata")
        self.tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
        )
        self.tree.heading("name", text="File")
        self.tree.heading("size", text="Size")
        self.tree.heading("metadata", text="Metadata detected")
        self.tree.column("name", width=320, anchor=tk.W)
        self.tree.column("size", width=90, anchor=tk.E)
        self.tree.column("metadata", width=360, anchor=tk.W)

        yscroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda e: self._open_selected_in_studio())
        self.tree.tag_configure("has_meta", foreground=self._colors["warn"])
        self.tree.tag_configure("clean", foreground=self._colors["success"])

        detail_frame = ttk.Frame(root)
        detail_frame.pack(fill=tk.BOTH, expand=False, padx=12, pady=(0, 4))
        ttk.Label(detail_frame, text="Activity log", style="Muted.TLabel").pack(anchor=tk.W)
        self.log = tk.Text(
            detail_frame,
            height=6,
            wrap=tk.WORD,
            bg=self._colors["surface"],
            fg=self._colors["fg"],
            insertbackground=self._colors["fg"],
            relief=tk.FLAT,
            font=("Consolas", 9),
            padx=8,
            pady=6,
        )
        self.log.pack(fill=tk.BOTH, expand=True)
        self.log.configure(state=tk.DISABLED)

        out_row = ttk.Frame(root)
        out_row.pack(fill=tk.X, padx=12, pady=4)
        self._reg(ttk.Label(out_row), "text", "output_folder").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Entry(out_row, textvariable=self.output_dir).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8)
        )
        self._reg(ttk.Button(out_row, command=self._browse_output), "text", "browse").pack(
            side=tk.LEFT
        )

        opts = ttk.Frame(root)
        opts.pack(fill=tk.X, padx=12, pady=4)
        self._reg(ttk.Label(opts), "text", "filename_suffix").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Entry(opts, textvariable=self.suffix_var, width=12).pack(side=tk.LEFT, padx=(0, 16))
        self._reg(
            ttk.Checkbutton(opts, variable=self.overwrite_var), "text", "overwrite_output"
        ).pack(side=tk.LEFT, padx=(0, 12))
        self._reg(ttk.Checkbutton(opts, variable=self.keep_icc_var), "text", "keep_icc").pack(
            side=tk.LEFT
        )

        action = ttk.Frame(root)
        action.pack(fill=tk.X, padx=12, pady=(8, 12))
        self.progress = ttk.Progressbar(
            action,
            variable=self.progress_var,
            maximum=100,
            mode="determinate",
        )
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 12))
        self.shred_btn = self._reg(
            ttk.Button(action, style="Accent.TButton", command=self._start_shred),
            "text",
            "shred_save",
        )
        self.shred_btn.pack(side=tk.RIGHT)

    # -- Studio tab ----------------------------------------------------------

    def _build_studio_tab(self, root: ttk.Frame) -> None:
        tools = ttk.Frame(root)
        tools.pack(fill=tk.X, padx=12, pady=(10, 0))
        self._reg(ttk.Button(tools, command=self._studio_open), "text", "open_image").pack(
            side=tk.LEFT, padx=(0, 6)
        )
        self._reg(ttk.Button(tools, command=self._studio_reload), "text", "reload").pack(
            side=tk.LEFT, padx=(0, 6)
        )
        self._reg(
            ttk.Button(tools, style="Danger.TButton", command=self._studio_clear_tags),
            "text",
            "clear_all_tags",
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Label(tools, textvariable=self.studio_file_label, style="Muted.TLabel").pack(
            side=tk.LEFT, padx=(12, 0)
        )

        # Split: tag table + editor
        mid = ttk.Frame(root)
        mid.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        table_frame = ttk.Frame(mid, style="Surface.TFrame")
        table_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("ifd", "id", "name", "value")
        self.studio_tree = ttk.Treeview(
            table_frame,
            columns=cols,
            show="headings",
            selectmode="browse",
        )
        self.studio_tree.heading("ifd", text="IFD")
        self.studio_tree.heading("id", text="ID")
        self.studio_tree.heading("name", text="Tag")
        self.studio_tree.heading("value", text="Value")
        self.studio_tree.column("ifd", width=80, anchor=tk.W)
        self.studio_tree.column("id", width=60, anchor=tk.E)
        self.studio_tree.column("name", width=160, anchor=tk.W)
        self.studio_tree.column("value", width=420, anchor=tk.W)

        sy = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.studio_tree.yview)
        self.studio_tree.configure(yscrollcommand=sy.set)
        self.studio_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sy.pack(side=tk.RIGHT, fill=tk.Y)
        self.studio_tree.bind("<<TreeviewSelect>>", self._studio_on_select)
        self.studio_tree.bind("<Double-1>", lambda e: self._studio_focus_editor())

        # Row editor
        editor = self._reg(ttk.LabelFrame(root), "text", "tag_editor")
        editor.pack(fill=tk.X, padx=12, pady=(0, 6))

        er1 = ttk.Frame(editor)
        er1.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(er1, text="IFD").pack(side=tk.LEFT, padx=(0, 6))
        self.edit_ifd = ttk.Combobox(
            er1, values=list(IFD_NAMES), width=10, state="readonly"
        )
        self.edit_ifd.set("0th")
        self.edit_ifd.pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(er1, text="Tag").pack(side=tk.LEFT, padx=(0, 6))
        self.edit_tag = ttk.Combobox(er1, width=28)
        self.edit_tag["values"] = [f"{n} ({i})" for _, i, n, _ in COMMON_TAGS]
        self.edit_tag.pack(side=tk.LEFT, padx=(0, 12))
        self.edit_tag.bind("<<ComboboxSelected>>", self._studio_tag_picked)
        ttk.Label(er1, text="or ID").pack(side=tk.LEFT, padx=(0, 6))
        self.edit_tag_id = ttk.Entry(er1, width=8)
        self.edit_tag_id.pack(side=tk.LEFT, padx=(0, 12))

        er2 = ttk.Frame(editor)
        er2.pack(fill=tk.X, padx=8, pady=(0, 6))
        self._reg(ttk.Label(er2), "text", "value").pack(side=tk.LEFT, padx=(0, 6))
        self.edit_value = ttk.Entry(er2)
        self.edit_value.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self._reg(
            ttk.Button(er2, command=self._studio_apply_editor), "text", "apply_to_row"
        ).pack(side=tk.LEFT, padx=(0, 6))
        self._reg(ttk.Button(er2, command=self._studio_add_tag), "text", "add_tag").pack(
            side=tk.LEFT, padx=(0, 6)
        )
        self._reg(
            ttk.Button(er2, style="Danger.TButton", command=self._studio_delete_tag),
            "text",
            "delete_tag",
        ).pack(side=tk.LEFT)

        # Quick fields
        quick = self._reg(ttk.LabelFrame(root), "text", "quick_fields")
        quick.pack(fill=tk.X, padx=12, pady=(0, 6))

        grid = ttk.Frame(quick)
        grid.pack(fill=tk.X, padx=8, pady=6)

        quick_layout = [
            ("Make", "Model", "Software"),
            ("Artist", "Copyright", "ImageDescription"),
            ("DateTime", "DateTimeOriginal", "DateTimeDigitized"),
            ("LensModel", "FNumber", "ISOSpeedRatings"),
            ("ExposureTime", "FocalLength", "UserComment"),
            ("GPSLatitude", "GPSLatitudeRef", "GPSAltitude"),
            ("GPSLongitude", "GPSLongitudeRef", "GPSAltitudeRef"),
        ]
        for r, names in enumerate(quick_layout):
            for c, name in enumerate(names):
                cell = ttk.Frame(grid)
                cell.grid(row=r, column=c, sticky="ew", padx=4, pady=2)
                ttk.Label(cell, text=name, style="Muted.TLabel").pack(anchor=tk.W)
                var = tk.StringVar()
                self._quick_vars[name] = var
                ttk.Entry(cell, textvariable=var).pack(fill=tk.X)
        for c in range(3):
            grid.columnconfigure(c, weight=1)

        qbtn = ttk.Frame(quick)
        qbtn.pack(fill=tk.X, padx=8, pady=(0, 8))
        self._reg(
            ttk.Button(qbtn, command=self._studio_apply_quick), "text", "apply_quick"
        ).pack(side=tk.LEFT, padx=(0, 8))
        self._reg(
            ttk.Button(qbtn, command=self._studio_pull_quick), "text", "pull_quick"
        ).pack(side=tk.LEFT)
        self._reg(ttk.Label(qbtn, style="Muted.TLabel"), "text", "gps_hint").pack(side=tk.RIGHT)

        # Output + write
        out_row = ttk.Frame(root)
        out_row.pack(fill=tk.X, padx=12, pady=4)
        self._reg(ttk.Label(out_row), "text", "output_folder").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Entry(out_row, textvariable=self.studio_output_dir).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8)
        )
        self._reg(
            ttk.Button(out_row, command=self._studio_browse_output), "text", "browse"
        ).pack(side=tk.LEFT)

        opts = ttk.Frame(root)
        opts.pack(fill=tk.X, padx=12, pady=4)
        self._reg(ttk.Label(opts), "text", "filename_suffix").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Entry(opts, textvariable=self.studio_suffix, width=12).pack(side=tk.LEFT, padx=(0, 16))
        self._reg(
            ttk.Checkbutton(opts, variable=self.studio_overwrite), "text", "overwrite_output"
        ).pack(side=tk.LEFT, padx=(0, 12))
        self._reg(
            ttk.Checkbutton(opts, variable=self.studio_inplace), "text", "overwrite_source"
        ).pack(side=tk.LEFT)

        action = ttk.Frame(root)
        action.pack(fill=tk.X, padx=12, pady=(8, 12))
        ttk.Label(action, textvariable=self.studio_status, style="Muted.TLabel").pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        self.studio_write_btn = self._reg(
            ttk.Button(action, style="Accent.TButton", command=self._studio_write),
            "text",
            "write_exif",
        )
        self.studio_write_btn.pack(side=tk.RIGHT)

    # -- Shared helpers ------------------------------------------------------

    def _log(self, message: str, tag: str | None = None) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, message + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.shred_btn.configure(state=state)
        self.studio_write_btn.configure(state=state)
        if hasattr(self, "pdf_write_btn"):
            self.pdf_write_btn.configure(state=state)
        if hasattr(self, "pdf_shred_btn"):
            self.pdf_shred_btn.configure(state=state)

    def _format_size(self, path: Path) -> str:
        try:
            n = path.stat().st_size
        except OSError:
            return "?"
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024:
                return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} TB"

    def _refresh_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for path in self.file_list:
            tags_list = inspect_metadata(path)
            meta_text = ", ".join(tags_list) if tags_list else "None"
            tag = "has_meta" if tags_list else "clean"
            self.tree.insert(
                "",
                tk.END,
                iid=str(path),
                values=(path.name, self._format_size(path), meta_text),
                tags=(tag,),
            )
        count = len(self.file_list)
        dirty = sum(1 for p in self.file_list if inspect_metadata(p))
        self.status_var.set(
            f"{count} image(s) queued · {dirty} with metadata"
            if count
            else "Add images to begin."
        )

    def _add_paths(self, paths: list[Path]) -> None:
        images = collect_images(paths, recursive=self.recursive_var.get())
        if not images:
            messagebox.showinfo(APP_NAME, "No supported images found.")
            return
        existing = set(self.file_list)
        added = 0
        for img in images:
            if img not in existing:
                self.file_list.append(img)
                existing.add(img)
                added += 1
        self._refresh_tree()
        self._log(f"Added {added} image(s). Total: {len(self.file_list)}")

    # -- Shred commands ------------------------------------------------------

    def _add_files(self) -> None:
        if self._busy:
            return
        filetypes = [
            (
                "Images",
                "*.jpg *.jpeg *.jpe *.jfif *.png *.tif *.tiff *.webp *.bmp *.gif *.ico",
            ),
            ("All files", "*.*"),
        ]
        paths = filedialog.askopenfilenames(title="Select images", filetypes=filetypes)
        if paths:
            self._add_paths([Path(p) for p in paths])

    def _add_folder(self) -> None:
        if self._busy:
            return
        folder = filedialog.askdirectory(title="Select folder of images")
        if folder:
            self._add_paths([Path(folder)])

    def _remove_selected(self) -> None:
        if self._busy:
            return
        selected = self.tree.selection()
        if not selected:
            return
        remove_set = {Path(s) for s in selected}
        self.file_list = [p for p in self.file_list if p not in remove_set]
        self._refresh_tree()
        self._log(f"Removed {len(selected)} item(s).")

    def _clear_all(self) -> None:
        if self._busy:
            return
        if not self.file_list:
            return
        if messagebox.askyesno(APP_NAME, "Clear the entire queue?"):
            self.file_list.clear()
            self._refresh_tree()
            self._log("Queue cleared.")

    def _browse_output(self) -> None:
        folder = filedialog.askdirectory(
            title="Choose output folder",
            initialdir=self.output_dir.get() or str(Path.home()),
        )
        if folder:
            self.output_dir.set(folder)

    def _on_select(self, _event=None) -> None:
        selected = self.tree.selection()
        if len(selected) == 1:
            path = Path(selected[0])
            tags = inspect_metadata(path)
            self.status_var.set(f"{path.name}  ·  {', '.join(tags) if tags else 'No metadata'}")

    def _paste_paths(self, _event=None) -> None:
        if self._busy:
            return
        if self.notebook.index(self.notebook.select()) == 1:
            return
        try:
            clip = self.clipboard_get()
        except tk.TclError:
            return
        paths = []
        for line in clip.replace("\r", "").split("\n"):
            line = line.strip().strip('"')
            if line and Path(line).exists():
                paths.append(Path(line))
        if paths:
            self._add_paths(paths)

    def _open_selected_in_studio(self) -> None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo(APP_NAME, "Select an image in the queue first.")
            return
        path = Path(selected[0])
        self.notebook.select(self.studio_tab)
        self._studio_load(path)

    def _start_shred(self) -> None:
        if self._busy:
            return
        if not self.file_list:
            messagebox.showwarning(APP_NAME, "Add at least one image first.")
            return
        out = Path(self.output_dir.get().strip())
        if not self.output_dir.get().strip():
            messagebox.showwarning(APP_NAME, "Choose an output folder.")
            return

        suffix = self.suffix_var.get()
        self._set_busy(True)
        self.progress_var.set(0)
        self.status_var.set("Shredding…")
        self._log(f"—— Shredding {len(self.file_list)} file(s) → {out} ——")

        sources = list(self.file_list)
        keep_icc = self.keep_icc_var.get()
        overwrite = self.overwrite_var.get()

        def worker() -> None:
            def on_progress(i: int, total: int, res: StripResult) -> None:
                pct = (i / total) * 100

                def ui_update() -> None:
                    self.progress_var.set(pct)
                    icon = "✓" if res.success else "✗"
                    self._log(f"{icon} {res.source.name}: {res.message}")
                    self.status_var.set(f"Processing {i}/{total}…")

                self.after(0, ui_update)

            try:
                results = batch_strip(
                    sources,
                    out,
                    suffix=suffix,
                    keep_icc=keep_icc,
                    overwrite=overwrite,
                    on_progress=on_progress,
                )
            except Exception as exc:
                self.after(0, lambda: self._finish_shred([], error=str(exc)))
                return
            self.after(0, lambda: self._finish_shred(results))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_shred(self, results: list[StripResult], error: str | None = None) -> None:
        self._set_busy(False)
        self.progress_var.set(100 if results else 0)
        if error:
            self.status_var.set("Failed.")
            self._log(f"Fatal error: {error}")
            messagebox.showerror(APP_NAME, error)
            return

        ok = sum(1 for r in results if r.success)
        fail = len(results) - ok
        stripped = sum(1 for r in results if r.success and r.had_metadata)
        self.status_var.set(f"Done · {ok} saved · {stripped} had metadata stripped · {fail} failed")
        self._log(f"Finished: {ok} ok, {fail} failed, {stripped} with metadata removed.")

        if fail and ok:
            messagebox.showwarning(
                APP_NAME,
                f"Completed with errors.\n\nSaved: {ok}\nFailed: {fail}\n\nSee the activity log for details.",
            )
        elif fail and not ok:
            messagebox.showerror(APP_NAME, f"All {fail} file(s) failed. See the activity log.")
        else:
            out = self.output_dir.get()
            if messagebox.askyesno(
                APP_NAME,
                f"All {ok} image(s) saved cleanly.\n\nOpen output folder?",
            ):
                self._open_folder(Path(out))

    def _open_folder(self, path: Path) -> None:
        try:
            path.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not open folder:\n{exc}")

    # -- Studio commands -----------------------------------------------------

    def _studio_open(self) -> None:
        if self._busy:
            return
        filetypes = [
            (
                "Images",
                "*.jpg *.jpeg *.jpe *.jfif *.png *.tif *.tiff *.webp *.bmp *.gif *.ico",
            ),
            ("JPEG (best EXIF support)", "*.jpg *.jpeg *.jpe *.jfif"),
            ("All files", "*.*"),
        ]
        path = filedialog.askopenfilename(title="Open image for EXIF Studio", filetypes=filetypes)
        if path:
            self._studio_load(Path(path))

    def _studio_load(self, path: Path) -> None:
        path = path.resolve()
        if not path.is_file():
            messagebox.showerror(APP_NAME, f"File not found:\n{path}")
            return
        self.studio_path = path
        self.studio_file_label.set(str(path))
        try:
            self.studio_rows = load_exif_rows(path)
        except Exception as exc:
            self.studio_rows = []
            messagebox.showwarning(
                APP_NAME,
                f"Could not read EXIF (you can still add tags):\n{exc}",
            )
        self._studio_refresh_table()
        self._studio_pull_quick()
        ext = path.suffix.lower()
        note = ""
        if ext not in PIEXIF_NATIVE_EXT:
            note = "  ·  Tip: JPEG supports lossless EXIF rewrite; other formats re-encode."
        self.studio_status.set(f"Loaded {len(self.studio_rows)} tag(s).{note}")
        self.status_var.set(f"Studio · {path.name} · {len(self.studio_rows)} tags")

    def _studio_reload(self) -> None:
        if self.studio_path:
            self._studio_load(self.studio_path)
        else:
            messagebox.showinfo(APP_NAME, "No image loaded.")

    def _studio_clear_tags(self) -> None:
        if not self.studio_rows:
            return
        if messagebox.askyesno(APP_NAME, "Remove all tags from the editor table?"):
            self.studio_rows.clear()
            self._studio_refresh_table()
            for v in self._quick_vars.values():
                v.set("")
            self.studio_status.set("All tags cleared (not saved yet).")

    def _studio_refresh_table(self) -> None:
        self.studio_tree.delete(*self.studio_tree.get_children())
        # Sort for readability: IFD order then tag id
        ifd_order = {n: i for i, n in enumerate(IFD_NAMES)}
        ordered = sorted(
            self.studio_rows,
            key=lambda r: (ifd_order.get(r.ifd, 99), r.tag_id),
        )
        self.studio_rows = ordered
        for i, row in enumerate(self.studio_rows):
            self.studio_tree.insert(
                "",
                tk.END,
                iid=str(i),
                values=(row.ifd, row.tag_id, row.name, row.value_display),
            )

    def _studio_on_select(self, _event=None) -> None:
        sel = self.studio_tree.selection()
        if not sel:
            return
        try:
            idx = int(sel[0])
        except ValueError:
            return
        if idx < 0 or idx >= len(self.studio_rows):
            return
        row = self.studio_rows[idx]
        self.edit_ifd.set(row.ifd)
        self.edit_tag.set(f"{row.name} ({row.tag_id})")
        self.edit_tag_id.delete(0, tk.END)
        self.edit_tag_id.insert(0, str(row.tag_id))
        self.edit_value.delete(0, tk.END)
        self.edit_value.insert(0, row.value_display)

    def _studio_focus_editor(self) -> None:
        self.edit_value.focus_set()
        self.edit_value.selection_range(0, tk.END)

    def _studio_tag_picked(self, _event=None) -> None:
        text = self.edit_tag.get()
        # "Make (271)" or free text
        m = re.search(r"\((\d+)\)\s*$", text)
        if m:
            self.edit_tag_id.delete(0, tk.END)
            self.edit_tag_id.insert(0, m.group(1))
            # Match IFD from catalog
            tag_id = int(m.group(1))
            for ifd, tid, name, _ in COMMON_TAGS:
                if tid == tag_id and name in text:
                    self.edit_ifd.set(ifd)
                    break

    def _resolve_editor_tag(self) -> tuple[str, int, str] | None:
        ifd = self.edit_ifd.get().strip() or "0th"
        if ifd not in IFD_NAMES:
            messagebox.showwarning(APP_NAME, f"IFD must be one of: {', '.join(IFD_NAMES)}")
            return None
        tid_text = self.edit_tag_id.get().strip()
        if not tid_text:
            # try parse from tag combobox
            m = re.search(r"\((\d+)\)\s*$", self.edit_tag.get())
            if m:
                tid_text = m.group(1)
        if not tid_text:
            messagebox.showwarning(APP_NAME, "Enter a tag ID (or pick a common tag).")
            return None
        try:
            tag_id = int(tid_text)
        except ValueError:
            messagebox.showwarning(APP_NAME, "Tag ID must be an integer.")
            return None
        name = _tag_name(ifd, tag_id)
        # Prefer name from combobox if it looks like a name
        combo = self.edit_tag.get().strip()
        if combo and not re.fullmatch(r"\d+", combo):
            name_part = re.sub(r"\s*\(\d+\)\s*$", "", combo).strip()
            if name_part:
                name = name_part
        return ifd, tag_id, name

    def _studio_apply_editor(self) -> None:
        resolved = self._resolve_editor_tag()
        if not resolved:
            return
        ifd, tag_id, name = resolved
        value = self.edit_value.get()
        sel = self.studio_tree.selection()
        row = ExifRow(ifd=ifd, tag_id=tag_id, name=name, value_display=value, raw_value=None)

        if sel:
            idx = int(sel[0])
            # Also update any other row with same ifd+id
            self.studio_rows[idx] = row
            # Deduplicate same key
            self.studio_rows = self._dedupe_rows(self.studio_rows)
        else:
            # Upsert by key
            found = False
            for i, r in enumerate(self.studio_rows):
                if r.ifd == ifd and r.tag_id == tag_id:
                    self.studio_rows[i] = row
                    found = True
                    break
            if not found:
                self.studio_rows.append(row)
        self._studio_refresh_table()
        self.studio_status.set(f"Updated {name} = {value}")

    def _studio_add_tag(self) -> None:
        resolved = self._resolve_editor_tag()
        if not resolved:
            return
        ifd, tag_id, name = resolved
        value = self.edit_value.get()
        row = ExifRow(ifd=ifd, tag_id=tag_id, name=name, value_display=value, raw_value=None)
        replaced = False
        for i, r in enumerate(self.studio_rows):
            if r.ifd == ifd and r.tag_id == tag_id:
                self.studio_rows[i] = row
                replaced = True
                break
        if not replaced:
            self.studio_rows.append(row)
        self._studio_refresh_table()
        self.studio_status.set(
            f"{'Replaced' if replaced else 'Added'} {ifd}/{name}"
        )

    def _studio_delete_tag(self) -> None:
        sel = self.studio_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "Select a tag row to delete.")
            return
        idx = int(sel[0])
        if 0 <= idx < len(self.studio_rows):
            removed = self.studio_rows.pop(idx)
            self._studio_refresh_table()
            self.studio_status.set(f"Deleted {removed.name}")

    @staticmethod
    def _dedupe_rows(rows: list[ExifRow]) -> list[ExifRow]:
        seen: dict[tuple[str, int], ExifRow] = {}
        for r in rows:
            seen[(r.ifd, r.tag_id)] = r
        return list(seen.values())

    def _studio_apply_quick(self) -> None:
        fields = {k: v.get() for k, v in self._quick_vars.items()}
        self.studio_rows = apply_quick_fields_to_rows(self.studio_rows, fields)
        self.studio_rows = self._dedupe_rows(self.studio_rows)
        self._studio_refresh_table()
        filled = sum(1 for v in fields.values() if v.strip())
        self.studio_status.set(f"Applied {filled} quick field(s) into the table.")

    def _studio_pull_quick(self) -> None:
        values = rows_to_quick_field_values(self.studio_rows)
        for k, var in self._quick_vars.items():
            var.set(values.get(k, ""))
        self.studio_status.set("Quick fields refreshed from table.")

    def _studio_browse_output(self) -> None:
        folder = filedialog.askdirectory(
            title="Choose Studio output folder",
            initialdir=self.studio_output_dir.get() or str(Path.home()),
        )
        if folder:
            self.studio_output_dir.set(folder)

    def _studio_write(self) -> None:
        if self._busy:
            return
        if not self.studio_path:
            messagebox.showwarning(APP_NAME, "Open an image first.")
            return
        if not self.studio_rows:
            if not messagebox.askyesno(
                APP_NAME,
                "No tags in the table. Writing will store empty EXIF.\nContinue?",
            ):
                return

        inplace = self.studio_inplace.get()
        if inplace:
            if not messagebox.askyesno(
                APP_NAME,
                f"Overwrite the original file in-place?\n\n{self.studio_path}\n\n"
                "This cannot be undone.",
            ):
                return
        else:
            if not self.studio_output_dir.get().strip():
                messagebox.showwarning(APP_NAME, "Choose an output folder.")
                return

        self._set_busy(True)
        self.studio_status.set("Writing EXIF…")
        self.status_var.set("Studio · writing…")

        source = self.studio_path
        rows = list(self.studio_rows)
        out_dir = Path(self.studio_output_dir.get().strip() or ".")
        suffix = self.studio_suffix.get()
        overwrite = self.studio_overwrite.get()

        def worker() -> None:
            try:
                res = write_exif_to_image(
                    source,
                    out_dir,
                    rows,
                    suffix=suffix,
                    overwrite=overwrite,
                    overwrite_source=inplace,
                )
            except Exception as exc:
                self.after(0, lambda: self._studio_write_done(None, str(exc)))
                return
            self.after(0, lambda: self._studio_write_done(res, None))

        threading.Thread(target=worker, daemon=True).start()

    def _studio_write_done(self, res: WriteResult | None, error: str | None) -> None:
        self._set_busy(False)
        if error:
            self.studio_status.set("Write failed.")
            self.status_var.set("Studio · failed")
            messagebox.showerror(APP_NAME, error)
            return
        assert res is not None
        if not res.success:
            self.studio_status.set(res.message)
            self.status_var.set("Studio · failed")
            messagebox.showerror(APP_NAME, res.message)
            return

        self.studio_status.set(res.message)
        self.status_var.set(f"Studio · {res.message}")
        self._log(f"Studio: {res.source.name} → {res.message}")

        # Reload from written file so table matches disk
        if res.output and res.output.is_file():
            if not self.studio_inplace.get():
                # Keep editing the original unless in-place; offer to open output
                if messagebox.askyesno(
                    APP_NAME,
                    f"EXIF written successfully.\n\n{res.output}\n\nOpen output folder?",
                ):
                    self._open_folder(res.output.parent)
            else:
                self._studio_load(res.output)
                messagebox.showinfo(APP_NAME, "Source updated in-place.")

    # -- PDF Data Studio tab -------------------------------------------------

    def _build_pdf_tab(self, root: ttk.Frame) -> None:
        tools = ttk.Frame(root)
        tools.pack(fill=tk.X, padx=12, pady=(10, 0))
        self._reg(ttk.Button(tools, command=self._pdf_open), "text", "open_pdf").pack(
            side=tk.LEFT, padx=(0, 6)
        )
        self._reg(ttk.Button(tools, command=self._pdf_reload), "text", "reload").pack(
            side=tk.LEFT, padx=(0, 6)
        )
        self._reg(
            ttk.Button(tools, style="Danger.TButton", command=self._pdf_clear_table),
            "text",
            "clear_meta",
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Label(tools, textvariable=self.pdf_file_label, style="Muted.TLabel").pack(
            side=tk.LEFT, padx=(12, 0)
        )

        # Split: file data | metadata
        paned = ttk.Frame(root)
        paned.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        left = self._reg(ttk.LabelFrame(paned), "text", "file_data")
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
        right = self._reg(ttk.LabelFrame(paned), "text", "doc_metadata")
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))

        # File info tree
        fi_cols = ("field", "value")
        self.pdf_info_tree = ttk.Treeview(left, columns=fi_cols, show="headings", selectmode="browse")
        self.pdf_info_tree.heading("field", text="Field")
        self.pdf_info_tree.heading("value", text="Value")
        self.pdf_info_tree.column("field", width=160, anchor=tk.W)
        self.pdf_info_tree.column("value", width=280, anchor=tk.W)
        fi_sy = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.pdf_info_tree.yview)
        self.pdf_info_tree.configure(yscrollcommand=fi_sy.set)
        self.pdf_info_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 0), pady=4)
        fi_sy.pack(side=tk.RIGHT, fill=tk.Y, pady=4)

        # Metadata tree
        md_cols = ("group", "key", "value")
        self.pdf_meta_tree = ttk.Treeview(
            right, columns=md_cols, show="headings", selectmode="browse"
        )
        self.pdf_meta_tree.heading("group", text="Group")
        self.pdf_meta_tree.heading("key", text="Key")
        self.pdf_meta_tree.heading("value", text="Value")
        self.pdf_meta_tree.column("group", width=80, anchor=tk.W)
        self.pdf_meta_tree.column("key", width=120, anchor=tk.W)
        self.pdf_meta_tree.column("value", width=260, anchor=tk.W)
        md_sy = ttk.Scrollbar(right, orient=tk.VERTICAL, command=self.pdf_meta_tree.yview)
        self.pdf_meta_tree.configure(yscrollcommand=md_sy.set)
        self.pdf_meta_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 0), pady=4)
        md_sy.pack(side=tk.RIGHT, fill=tk.Y, pady=4)
        self.pdf_meta_tree.bind("<<TreeviewSelect>>", self._pdf_on_select)
        self.pdf_meta_tree.bind("<Double-1>", lambda e: self._pdf_focus_editor())

        # Field editor
        editor = ttk.LabelFrame(root, text="Field editor")
        editor.pack(fill=tk.X, padx=12, pady=(0, 6))
        er1 = ttk.Frame(editor)
        er1.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(er1, text="Key").pack(side=tk.LEFT, padx=(0, 6))
        self.pdf_edit_key = ttk.Combobox(er1, width=22, values=PDF_COMMON_KEYS)
        self.pdf_edit_key.pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(er1, text="Value").pack(side=tk.LEFT, padx=(0, 6))
        self.pdf_edit_value = ttk.Entry(er1)
        self.pdf_edit_value.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ttk.Button(er1, text="Apply", command=self._pdf_apply_editor).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(er1, text="Add Field", command=self._pdf_add_field).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            er1, text="Delete Field", style="Danger.TButton", command=self._pdf_delete_field
        ).pack(side=tk.LEFT)

        # Quick fields
        quick = ttk.LabelFrame(root, text="Quick fields  ·  fill any, then Apply Quick Fields")
        quick.pack(fill=tk.X, padx=12, pady=(0, 6))
        grid = ttk.Frame(quick)
        grid.pack(fill=tk.X, padx=8, pady=6)
        quick_layout = [
            ("Title", "Author", "Subject"),
            ("Keywords", "Creator", "Producer"),
            ("CreationDate", "ModDate", "Trapped"),
        ]
        for r, names in enumerate(quick_layout):
            for c, name in enumerate(names):
                cell = ttk.Frame(grid)
                cell.grid(row=r, column=c, sticky="ew", padx=4, pady=2)
                ttk.Label(cell, text=name, style="Muted.TLabel").pack(anchor=tk.W)
                var = tk.StringVar()
                self._pdf_quick_vars[name] = var
                ttk.Entry(cell, textvariable=var).pack(fill=tk.X)
        for c in range(3):
            grid.columnconfigure(c, weight=1)

        qbtn = ttk.Frame(quick)
        qbtn.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Button(qbtn, text="Apply Quick Fields → Table", command=self._pdf_apply_quick).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(qbtn, text="Pull Table → Quick Fields", command=self._pdf_pull_quick).pack(
            side=tk.LEFT
        )
        ttk.Label(
            qbtn,
            text="Dates: D:YYYYMMDDHHmmSS  or  2026-07-16 14:30:00",
            style="Muted.TLabel",
        ).pack(side=tk.RIGHT)

        # Output
        out_row = ttk.Frame(root)
        out_row.pack(fill=tk.X, padx=12, pady=4)
        self._reg(ttk.Label(out_row), "text", "output_folder").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Entry(out_row, textvariable=self.pdf_output_dir).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8)
        )
        self._reg(ttk.Button(out_row, command=self._pdf_browse_output), "text", "browse").pack(
            side=tk.LEFT
        )

        opts = ttk.Frame(root)
        opts.pack(fill=tk.X, padx=12, pady=4)
        self._reg(ttk.Label(opts), "text", "filename_suffix").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Entry(opts, textvariable=self.pdf_suffix, width=12).pack(side=tk.LEFT, padx=(0, 16))
        self._reg(
            ttk.Checkbutton(opts, variable=self.pdf_overwrite), "text", "overwrite_output"
        ).pack(side=tk.LEFT, padx=(0, 12))
        self._reg(
            ttk.Checkbutton(opts, variable=self.pdf_inplace), "text", "overwrite_source"
        ).pack(side=tk.LEFT, padx=(0, 12))
        self._reg(
            ttk.Checkbutton(opts, variable=self.pdf_strip_xmp), "text", "strip_xmp"
        ).pack(side=tk.LEFT)

        action = ttk.Frame(root)
        action.pack(fill=tk.X, padx=12, pady=(8, 12))
        ttk.Label(action, textvariable=self.pdf_status, style="Muted.TLabel").pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        self.pdf_shred_btn = self._reg(
            ttk.Button(action, style="Danger.TButton", command=self._pdf_shred),
            "text",
            "shred_pdf",
        )
        self.pdf_shred_btn.pack(side=tk.RIGHT, padx=(8, 0))
        self.pdf_write_btn = self._reg(
            ttk.Button(action, style="Accent.TButton", command=self._pdf_write),
            "text",
            "write_pdf",
        )
        self.pdf_write_btn.pack(side=tk.RIGHT)

    # -- Scramble / Mask tab -------------------------------------------------

    def _build_scramble_tab(self, root: ttk.Frame) -> None:
        head = ttk.Frame(root)
        head.pack(fill=tk.X, padx=12, pady=(10, 4))
        self._reg(ttk.Label(head, style="Title.TLabel"), "text", "scramble_title").pack(
            anchor=tk.W
        )
        self._reg(ttk.Label(head, style="Subtitle.TLabel"), "text", "scramble_help").pack(
            anchor=tk.W, pady=(2, 0)
        )

        pick = ttk.LabelFrame(root, text="")
        pick.pack(fill=tk.X, padx=12, pady=6)
        self._reg(pick, "text", "device_mask")

        row1 = ttk.Frame(pick)
        row1.pack(fill=tk.X, padx=8, pady=6)

        self._reg(ttk.Label(row1), "text", "category").pack(side=tk.LEFT, padx=(0, 6))
        self.scramble_cat_combo = ttk.Combobox(
            row1, textvariable=self.scramble_category, state="readonly", width=14
        )
        self.scramble_cat_combo.pack(side=tk.LEFT, padx=(0, 16))
        self.scramble_cat_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_mask_filters())

        self._reg(ttk.Label(row1), "text", "region").pack(side=tk.LEFT, padx=(0, 6))
        self.scramble_region_combo = ttk.Combobox(
            row1, textvariable=self.scramble_region, state="readonly", width=22
        )
        self.scramble_region_combo.pack(side=tk.LEFT, padx=(0, 16))
        self.scramble_region_combo.bind(
            "<<ComboboxSelected>>", lambda e: self._refresh_mask_filters()
        )

        self._reg(ttk.Label(row1), "text", "device_mask").pack(side=tk.LEFT, padx=(0, 6))
        self.scramble_mask_combo = ttk.Combobox(row1, state="readonly", width=42)
        self.scramble_mask_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.scramble_mask_combo.bind("<<ComboboxSelected>>", self._on_mask_picked)

        row2 = ttk.Frame(pick)
        row2.pack(fill=tk.X, padx=8, pady=(0, 8))
        self._reg(
            ttk.Button(row2, command=self._scramble_random), "text", "random_mask"
        ).pack(side=tk.LEFT, padx=(0, 8))
        self._reg(
            ttk.Button(row2, command=self._scramble_preview), "text", "preview_mask"
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(row2, textvariable=self.scramble_mask_count, style="Muted.TLabel").pack(
            side=tk.LEFT, padx=(12, 0)
        )

        opts = self._reg(ttk.LabelFrame(root), "text", "scramble_options")
        opts.pack(fill=tk.X, padx=12, pady=6)

        o1 = ttk.Frame(opts)
        o1.pack(fill=tk.X, padx=8, pady=6)
        self._reg(
            ttk.Checkbutton(o1, variable=self.scramble_opt_gps), "text", "opt_random_gps"
        ).pack(side=tk.LEFT, padx=(0, 16))
        self._reg(
            ttk.Checkbutton(o1, variable=self.scramble_opt_dt), "text", "opt_random_dt"
        ).pack(side=tk.LEFT, padx=(0, 16))
        self._reg(
            ttk.Checkbutton(o1, variable=self.scramble_opt_exp), "text", "opt_random_exp"
        ).pack(side=tk.LEFT, padx=(0, 16))
        self._reg(
            ttk.Checkbutton(o1, variable=self.scramble_opt_artist), "text", "opt_artist"
        ).pack(side=tk.LEFT)

        o2 = ttk.Frame(opts)
        o2.pack(fill=tk.X, padx=8, pady=(0, 4))
        self._reg(ttk.Label(o2), "text", "artist_name").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Entry(o2, textvariable=self.scramble_artist, width=22).pack(
            side=tk.LEFT, padx=(0, 16)
        )
        self._reg(ttk.Label(o2), "text", "user_comment").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Entry(o2, textvariable=self.scramble_comment).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )

        o3 = ttk.Frame(opts)
        o3.pack(fill=tk.X, padx=8, pady=(0, 8))
        self._reg(ttk.Label(o3), "text", "pdf_title").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Entry(o3, textvariable=self.scramble_pdf_title, width=18).pack(
            side=tk.LEFT, padx=(0, 10)
        )
        self._reg(ttk.Label(o3), "text", "pdf_author").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Entry(o3, textvariable=self.scramble_pdf_author, width=16).pack(
            side=tk.LEFT, padx=(0, 10)
        )
        self._reg(ttk.Label(o3), "text", "pdf_subject").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Entry(o3, textvariable=self.scramble_pdf_subject, width=16).pack(
            side=tk.LEFT, padx=(0, 10)
        )
        self._reg(ttk.Label(o3), "text", "pdf_keywords").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Entry(o3, textvariable=self.scramble_pdf_keywords).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )

        preview_frame = self._reg(ttk.LabelFrame(root), "text", "preview")
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
        self.scramble_preview = tk.Text(
            preview_frame,
            height=12,
            wrap=tk.WORD,
            bg=self._colors["surface"],
            fg=self._colors["fg"],
            insertbackground=self._colors["fg"],
            relief=tk.FLAT,
            font=("Consolas", 9),
            padx=10,
            pady=8,
        )
        self.scramble_preview.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.scramble_preview.configure(state=tk.DISABLED)

        actions = ttk.Frame(root)
        actions.pack(fill=tk.X, padx=12, pady=(4, 4))
        self._reg(
            ttk.Button(actions, style="Accent.TButton", command=self._scramble_apply_exif),
            "text",
            "apply_to_exif",
        ).pack(side=tk.LEFT, padx=(0, 8))
        self._reg(
            ttk.Button(actions, style="Accent.TButton", command=self._scramble_apply_pdf),
            "text",
            "apply_to_pdf",
        ).pack(side=tk.LEFT, padx=(0, 8))
        self._reg(
            ttk.Button(actions, command=self._scramble_batch_images),
            "text",
            "scramble_batch_images",
        ).pack(side=tk.LEFT, padx=(0, 16))
        self._reg(ttk.Label(actions), "text", "batch_suffix").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Entry(actions, textvariable=self.scramble_batch_suffix, width=12).pack(side=tk.LEFT)

        foot = ttk.Frame(root)
        foot.pack(fill=tk.X, padx=12, pady=(4, 12))
        ttk.Label(foot, textvariable=self.scramble_status, style="Muted.TLabel").pack(
            anchor=tk.W
        )

    def _category_key_from_display(self, display: str) -> str:
        if display == self.t("all") or display == "all":
            return "all"
        for cat in CATEGORIES:
            if display == self.t(f"cat_{cat}") or display == cat:
                return cat
        return "all"

    def _region_key_from_display(self, display: str) -> str:
        if display == self.t("all") or display == "all":
            return "all"
        for code, label in REGION_LABELS.items():
            if display == f"{code} — {label}" or display == code or display == label:
                return code
        # raw code stored in variable
        raw = self.scramble_region.get()
        if raw in REGION_LABELS or raw == "all":
            return raw
        return "all"

    def _update_category_labels(self) -> None:
        if not hasattr(self, "scramble_cat_combo"):
            return
        cat_values = [self.t("all")] + [self.t(f"cat_{c}") for c in CATEGORIES]
        # Preserve selection by key
        cur = self._category_key_from_display(self.scramble_category.get())
        self.scramble_cat_combo["values"] = cat_values
        if cur == "all":
            self.scramble_category.set(self.t("all"))
        else:
            self.scramble_category.set(self.t(f"cat_{cur}"))

        reg_values = [self.t("all")] + [
            f"{code} — {REGION_LABELS.get(code, code)}" for code in regions_present()
        ]
        cur_r = self._region_key_from_display(self.scramble_region.get())
        self.scramble_region_combo["values"] = reg_values
        if cur_r == "all":
            self.scramble_region.set(self.t("all"))
        else:
            self.scramble_region.set(f"{cur_r} — {REGION_LABELS.get(cur_r, cur_r)}")

    def _refresh_mask_filters(self, keep_selection: bool = False) -> None:
        if not hasattr(self, "scramble_mask_combo"):
            return
        self._update_category_labels()
        cat = self._category_key_from_display(self.scramble_category.get())
        reg = self._region_key_from_display(self.scramble_region.get())
        pool = filter_masks(
            category=None if cat == "all" else cat,
            region=None if reg == "all" else reg,
        )
        self._mask_id_by_label = {
            f"{m.label}  [{m.region}/{m.category}]": m.id for m in pool
        }
        labels = list(self._mask_id_by_label.keys())
        self.scramble_mask_combo["values"] = labels
        self.scramble_mask_count.set(self.t("mask_count", n=len(pool)))

        prev_id = self.scramble_mask_id.get() if keep_selection else ""
        if prev_id and any(m.id == prev_id for m in pool):
            for label, mid in self._mask_id_by_label.items():
                if mid == prev_id:
                    self.scramble_mask_combo.set(label)
                    break
        elif labels:
            self.scramble_mask_combo.set(labels[0])
            self.scramble_mask_id.set(self._mask_id_by_label[labels[0]])
        else:
            self.scramble_mask_combo.set("")
            self.scramble_mask_id.set("")

    def _on_mask_picked(self, _event: Any = None) -> None:
        label = self.scramble_mask_combo.get()
        mid = self._mask_id_by_label.get(label, "")
        self.scramble_mask_id.set(mid)

    def _current_mask(self) -> DeviceMask | None:
        mid = self.scramble_mask_id.get()
        if mid:
            m = mask_by_id(mid)
            if m:
                return m
        label = self.scramble_mask_combo.get() if hasattr(self, "scramble_mask_combo") else ""
        mid = self._mask_id_by_label.get(label, "")
        return mask_by_id(mid) if mid else None

    def _scramble_options(self) -> ScrambleOptions:
        return ScrambleOptions(
            randomize_gps=self.scramble_opt_gps.get(),
            randomize_datetime=self.scramble_opt_dt.get(),
            randomize_exposure=self.scramble_opt_exp.get(),
            set_artist=self.scramble_opt_artist.get(),
            artist_name=self.scramble_artist.get(),
            user_comment=self.scramble_comment.get(),
            pdf_title=self.scramble_pdf_title.get(),
            pdf_author=self.scramble_pdf_author.get(),
            pdf_subject=self.scramble_pdf_subject.get(),
            pdf_keywords=self.scramble_pdf_keywords.get(),
        )

    def _show_scramble_preview(self, payload: ScramblePayload) -> None:
        self._last_payload = payload
        lines = [
            f"══ {payload.mask.label} ══",
            f"Category : {payload.mask.category}",
            f"Region   : {payload.mask.region} · {payload.mask.country}",
            f"City     : {payload.mask.city}",
            f"Locale   : {payload.mask.locale_hint}  TZ {payload.mask.timezone_offset}",
            "",
            "— EXIF fields —",
        ]
        for k, v in payload.exif_fields.items():
            lines.append(f"  {k:20s} = {v}")
        lines.append("")
        lines.append("— PDF Info fields —")
        for k, v in payload.pdf_fields.items():
            lines.append(f"  {k:20s} = {v}")
        lines.append("")
        lines.append(payload.summary)

        self.scramble_preview.configure(state=tk.NORMAL)
        self.scramble_preview.delete("1.0", tk.END)
        self.scramble_preview.insert(tk.END, "\n".join(lines))
        self.scramble_preview.configure(state=tk.DISABLED)
        self.scramble_status.set(payload.summary)
        self.status_var.set(f"Mask · {payload.mask.label}")

    def _scramble_random(self) -> None:
        cat = self._category_key_from_display(self.scramble_category.get())
        reg = self._region_key_from_display(self.scramble_region.get())
        mask = pick_random_mask(
            category=None if cat == "all" else cat,
            region=None if reg == "all" else reg,
        )
        # Select in combo if present
        for label, mid in self._mask_id_by_label.items():
            if mid == mask.id:
                self.scramble_mask_combo.set(label)
                self.scramble_mask_id.set(mid)
                break
        else:
            # Expand filters so the mask shows
            self.scramble_category.set(self.t("all"))
            self.scramble_region.set(self.t("all"))
            self._refresh_mask_filters()
            for label, mid in self._mask_id_by_label.items():
                if mid == mask.id:
                    self.scramble_mask_combo.set(label)
                    self.scramble_mask_id.set(mid)
                    break
        payload = build_scramble(mask, self._scramble_options())
        self._show_scramble_preview(payload)

    def _scramble_preview(self) -> None:
        mask = self._current_mask()
        if not mask:
            messagebox.showinfo(APP_NAME, self.t("no_mask"))
            return
        payload = build_scramble(mask, self._scramble_options())
        self._show_scramble_preview(payload)

    def _ensure_payload(self) -> ScramblePayload | None:
        if self._last_payload is not None:
            # Rebuild so options changes apply
            mask = self._current_mask() or self._last_payload.mask
            payload = build_scramble(mask, self._scramble_options())
            self._show_scramble_preview(payload)
            return payload
        mask = self._current_mask()
        if not mask:
            messagebox.showinfo(APP_NAME, self.t("no_mask"))
            return None
        payload = build_scramble(mask, self._scramble_options())
        self._show_scramble_preview(payload)
        return payload

    def _scramble_apply_exif(self) -> None:
        payload = self._ensure_payload()
        if not payload:
            return
        if not self.studio_path:
            # Still fill quick fields / empty table so user can open image later
            for key, var in self._quick_vars.items():
                var.set(payload.exif_fields.get(key, ""))
            self.studio_rows = apply_quick_fields_to_rows([], payload.exif_fields)
            self._studio_refresh_table()
            self.notebook.select(self.studio_tab)
            self.scramble_status.set(self.t("scramble_applied_exif"))
            self.studio_status.set(self.t("scramble_applied_exif"))
            messagebox.showinfo(
                APP_NAME,
                self.t("scramble_applied_exif") + "\n\n" + self.t("scramble_need_image"),
            )
            return

        for key, var in self._quick_vars.items():
            var.set(payload.exif_fields.get(key, var.get()))
        self.studio_rows = apply_quick_fields_to_rows(self.studio_rows, payload.exif_fields)
        self._studio_refresh_table()
        self.notebook.select(self.studio_tab)
        self.studio_status.set(self.t("scramble_applied_exif"))
        self.scramble_status.set(self.t("scramble_applied_exif"))
        self.status_var.set(f"Mask → EXIF · {payload.mask.label}")
        self._log(f"Mask applied to EXIF: {payload.mask.label}")

    def _scramble_apply_pdf(self) -> None:
        payload = self._ensure_payload()
        if not payload:
            return
        if not self.pdf_path:
            for key, var in self._pdf_quick_vars.items():
                var.set(payload.pdf_fields.get(key, ""))
            self.pdf_rows = apply_pdf_quick_fields([], payload.pdf_fields)
            self._pdf_refresh_meta()
            self.notebook.select(self.pdf_tab)
            self.scramble_status.set(self.t("scramble_applied_pdf"))
            messagebox.showinfo(
                APP_NAME,
                self.t("scramble_applied_pdf") + "\n\n" + self.t("scramble_need_pdf"),
            )
            return

        for key, var in self._pdf_quick_vars.items():
            if key in payload.pdf_fields:
                var.set(payload.pdf_fields[key])
        self.pdf_rows = apply_pdf_quick_fields(self.pdf_rows, payload.pdf_fields)
        self._pdf_refresh_meta()
        self.notebook.select(self.pdf_tab)
        self.pdf_status.set(self.t("scramble_applied_pdf"))
        self.scramble_status.set(self.t("scramble_applied_pdf"))
        self.status_var.set(f"Mask → PDF · {payload.mask.label}")
        self._log(f"Mask applied to PDF: {payload.mask.label}")

    def _scramble_batch_images(self) -> None:
        if self._busy:
            return
        if not self.file_list:
            messagebox.showinfo(APP_NAME, self.t("scramble_none_queued"))
            return
        payload = self._ensure_payload()
        if not payload:
            return

        out_dir = Path(self.output_dir.get().strip() or str(Path.home() / "Pictures" / "EXIFexit"))
        suffix = self.scramble_batch_suffix.get()
        overwrite = self.overwrite_var.get()
        sources = list(self.file_list)
        fields = dict(payload.exif_fields)
        mask_label = payload.mask.label

        self._set_busy(True)
        self.progress_var.set(0)
        self.status_var.set(f"Scrambling {len(sources)} image(s) as {mask_label}…")

        def worker() -> None:
            ok = 0
            total = len(sources)
            results: list[WriteResult] = []
            for i, src in enumerate(sources, start=1):
                try:
                    rows = load_exif_rows(src)
                    rows = apply_quick_fields_to_rows(rows, fields)
                    res = write_exif_to_image(
                        src,
                        out_dir,
                        rows,
                        suffix=suffix,
                        overwrite=overwrite,
                        overwrite_source=False,
                    )
                except Exception as exc:
                    res = WriteResult(source=src, success=False, message=str(exc))
                results.append(res)
                if res.success:
                    ok += 1
                pct = (i / total) * 100
                self.after(0, lambda p=pct, r=res: self._scramble_batch_progress(p, r))
            self.after(0, lambda: self._scramble_batch_done(ok, total, mask_label, out_dir))

        threading.Thread(target=worker, daemon=True).start()

    def _scramble_batch_progress(self, pct: float, res: WriteResult) -> None:
        self.progress_var.set(pct)
        if res.success:
            self._log(f"Masked · {res.source.name} → {res.message}")
        else:
            self._log(f"Failed · {res.source.name}: {res.message}")

    def _scramble_batch_done(
        self, ok: int, total: int, mask_label: str, out_dir: Path
    ) -> None:
        self._set_busy(False)
        self.progress_var.set(100)
        msg = self.t("scramble_batch_done", ok=ok, total=total)
        self.scramble_status.set(f"{msg}  ·  {mask_label}")
        self.status_var.set(msg)
        self._log(msg)
        if ok and messagebox.askyesno(APP_NAME, f"{msg}\n\n{self.t('open_folder_q')}"):
            self._open_folder(out_dir)

    def _pdf_open(self) -> None:
        if self._busy:
            return
        path = filedialog.askopenfilename(
            title="Open PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if path:
            self._pdf_load(Path(path))

    def _pdf_load(self, path: Path) -> None:
        path = path.resolve()
        if not path.is_file():
            messagebox.showerror(APP_NAME, f"File not found:\n{path}")
            return
        if path.suffix.lower() != ".pdf":
            messagebox.showwarning(APP_NAME, "Please select a .pdf file.")
            return
        self.pdf_path = path
        self.pdf_file_label.set(str(path))
        try:
            self.pdf_file_info = load_pdf_file_info(path)
            self.pdf_rows = load_pdf_metadata_rows(path)
        except Exception as exc:
            self.pdf_file_info = []
            self.pdf_rows = []
            messagebox.showerror(APP_NAME, f"Could not read PDF:\n{exc}")
            return
        self._pdf_refresh_info()
        self._pdf_refresh_meta()
        self._pdf_pull_quick()
        n_meta = sum(1 for r in self.pdf_rows if r.editable and r.value)
        self.pdf_status.set(
            f"Loaded · {len(self.pdf_file_info)} file fields · {n_meta} metadata value(s)"
        )
        self.status_var.set(f"PDF · {path.name} · {n_meta} fields set")

    def _pdf_reload(self) -> None:
        if self.pdf_path:
            self._pdf_load(self.pdf_path)
        else:
            messagebox.showinfo(APP_NAME, "No PDF loaded.")

    def _pdf_clear_table(self) -> None:
        if not self.pdf_rows:
            return
        if messagebox.askyesno(
            APP_NAME,
            "Clear all editable metadata values in the table?\n"
            "(Not saved until you Write or Shred.)",
        ):
            for i, r in enumerate(self.pdf_rows):
                if r.editable:
                    self.pdf_rows[i] = PdfMetaRow(
                        key=r.key, value="", group=r.group, editable=True
                    )
            # Drop custom empty extras? keep standard keys
            self.pdf_rows = [
                r
                for r in self.pdf_rows
                if r.group == "Document" or r.group == "XMP" or (r.group == "Custom" and r.value)
            ]
            # re-ensure standards
            have = {r.key.lower() for r in self.pdf_rows}
            for key in PDF_STANDARD_KEYS:
                if key.lower() not in have:
                    self.pdf_rows.append(
                        PdfMetaRow(key=key, value="", group="Document", editable=True)
                    )
            self._pdf_refresh_meta()
            for v in self._pdf_quick_vars.values():
                v.set("")
            self.pdf_status.set("Metadata fields cleared in editor (not saved yet).")

    def _pdf_refresh_info(self) -> None:
        self.pdf_info_tree.delete(*self.pdf_info_tree.get_children())
        for i, (label, value) in enumerate(self.pdf_file_info):
            self.pdf_info_tree.insert("", tk.END, iid=f"fi{i}", values=(label, value))

    def _pdf_refresh_meta(self) -> None:
        self.pdf_meta_tree.delete(*self.pdf_meta_tree.get_children())
        group_order = {"Document": 0, "Custom": 1, "XMP": 2}
        std_order = {k: i for i, k in enumerate(PDF_STANDARD_KEYS)}
        self.pdf_rows.sort(
            key=lambda r: (
                group_order.get(r.group, 9),
                std_order.get(r.key, 100),
                r.key.lower(),
            )
        )
        for i, row in enumerate(self.pdf_rows):
            self.pdf_meta_tree.insert(
                "",
                tk.END,
                iid=str(i),
                values=(row.group, row.key, row.value),
            )

    def _pdf_on_select(self, _event=None) -> None:
        sel = self.pdf_meta_tree.selection()
        if not sel:
            return
        try:
            idx = int(sel[0])
        except ValueError:
            return
        if idx < 0 or idx >= len(self.pdf_rows):
            return
        row = self.pdf_rows[idx]
        self.pdf_edit_key.set(row.key)
        self.pdf_edit_value.delete(0, tk.END)
        self.pdf_edit_value.insert(0, row.value)
        if not row.editable:
            self.pdf_status.set("XMP preview is observe-only. Use Shred to remove XMP.")

    def _pdf_focus_editor(self) -> None:
        self.pdf_edit_value.focus_set()
        self.pdf_edit_value.selection_range(0, tk.END)

    def _pdf_apply_editor(self) -> None:
        key = self.pdf_edit_key.get().strip()
        if not key:
            messagebox.showwarning(APP_NAME, "Enter a metadata key (e.g. Title).")
            return
        if key == "XMP_Preview":
            messagebox.showinfo(APP_NAME, "XMP preview is not editable.")
            return
        value = self.pdf_edit_value.get()
        if key in ("CreationDate", "ModDate"):
            value = normalize_pdf_date(value)
        group = "Document" if key in PDF_STANDARD_KEYS else "Custom"
        row = PdfMetaRow(key=key, value=value, group=group, editable=True)
        sel = self.pdf_meta_tree.selection()
        if sel:
            try:
                idx = int(sel[0])
                if 0 <= idx < len(self.pdf_rows) and self.pdf_rows[idx].editable:
                    self.pdf_rows[idx] = row
                else:
                    self._pdf_upsert_row(row)
            except ValueError:
                self._pdf_upsert_row(row)
        else:
            self._pdf_upsert_row(row)
        self.pdf_rows = self._pdf_dedupe(self.pdf_rows)
        self._pdf_refresh_meta()
        self.pdf_status.set(f"Updated {key}")

    def _pdf_add_field(self) -> None:
        key = self.pdf_edit_key.get().strip()
        if not key:
            messagebox.showwarning(APP_NAME, "Enter a metadata key.")
            return
        if key == "XMP_Preview":
            return
        value = self.pdf_edit_value.get()
        if key in ("CreationDate", "ModDate"):
            value = normalize_pdf_date(value)
        group = "Document" if key in PDF_STANDARD_KEYS else "Custom"
        self._pdf_upsert_row(PdfMetaRow(key=key, value=value, group=group, editable=True))
        self.pdf_rows = self._pdf_dedupe(self.pdf_rows)
        self._pdf_refresh_meta()
        self.pdf_status.set(f"Added/updated {key}")

    def _pdf_delete_field(self) -> None:
        sel = self.pdf_meta_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "Select a metadata field to delete.")
            return
        idx = int(sel[0])
        if 0 <= idx < len(self.pdf_rows):
            row = self.pdf_rows[idx]
            if not row.editable:
                messagebox.showinfo(APP_NAME, "This field is observe-only.")
                return
            if row.key in PDF_STANDARD_KEYS:
                # Clear rather than remove standards
                self.pdf_rows[idx] = PdfMetaRow(
                    key=row.key, value="", group=row.group, editable=True
                )
                self.pdf_status.set(f"Cleared {row.key}")
            else:
                self.pdf_rows.pop(idx)
                self.pdf_status.set(f"Deleted {row.key}")
            self._pdf_refresh_meta()

    def _pdf_upsert_row(self, row: PdfMetaRow) -> None:
        for i, r in enumerate(self.pdf_rows):
            if r.key.lower() == row.key.lower() and r.editable:
                self.pdf_rows[i] = row
                return
        self.pdf_rows.append(row)

    @staticmethod
    def _pdf_dedupe(rows: list[PdfMetaRow]) -> list[PdfMetaRow]:
        seen: dict[str, PdfMetaRow] = {}
        xmp: list[PdfMetaRow] = []
        for r in rows:
            if not r.editable:
                xmp.append(r)
                continue
            seen[r.key.lower()] = r
        return list(seen.values()) + xmp

    def _pdf_apply_quick(self) -> None:
        fields = {k: v.get() for k, v in self._pdf_quick_vars.items()}
        self.pdf_rows = apply_pdf_quick_fields(self.pdf_rows, fields)
        self.pdf_rows = self._pdf_dedupe(self.pdf_rows)
        self._pdf_refresh_meta()
        filled = sum(1 for v in fields.values() if v.strip())
        self.pdf_status.set(f"Applied {filled} quick field(s).")

    def _pdf_pull_quick(self) -> None:
        values = pdf_rows_to_quick_values(self.pdf_rows)
        for k, var in self._pdf_quick_vars.items():
            var.set(values.get(k, ""))
        self.pdf_status.set("Quick fields refreshed from table.")

    def _pdf_browse_output(self) -> None:
        folder = filedialog.askdirectory(
            title="Choose PDF output folder",
            initialdir=self.pdf_output_dir.get() or str(Path.home()),
        )
        if folder:
            self.pdf_output_dir.set(folder)

    def _pdf_write(self) -> None:
        self._pdf_run_write(strip_all=False)

    def _pdf_shred(self) -> None:
        if not self.pdf_path:
            messagebox.showwarning(APP_NAME, "Open a PDF first.")
            return
        if not messagebox.askyesno(
            APP_NAME,
            "Shred all document metadata"
            + (" and XMP" if self.pdf_strip_xmp.get() else "")
            + " from this PDF?\n\n"
            "A cleaned copy will be written (unless in-place overwrite is enabled).",
        ):
            return
        self._pdf_run_write(strip_all=True)

    def _pdf_run_write(self, *, strip_all: bool) -> None:
        if self._busy:
            return
        if not self.pdf_path:
            messagebox.showwarning(APP_NAME, "Open a PDF first.")
            return

        inplace = self.pdf_inplace.get()
        if inplace:
            if not messagebox.askyesno(
                APP_NAME,
                f"Overwrite the original PDF in-place?\n\n{self.pdf_path}\n\n"
                "This cannot be undone.",
            ):
                return
        else:
            if not self.pdf_output_dir.get().strip():
                messagebox.showwarning(APP_NAME, "Choose an output folder.")
                return

        self._set_busy(True)
        action = "Shredding" if strip_all else "Writing"
        self.pdf_status.set(f"{action} PDF metadata…")
        self.status_var.set(f"PDF · {action.lower()}…")

        source = self.pdf_path
        rows = list(self.pdf_rows)
        out_dir = Path(self.pdf_output_dir.get().strip() or ".")
        suffix = "_clean" if strip_all and self.pdf_suffix.get() == "_meta" else self.pdf_suffix.get()
        if strip_all and not self.pdf_suffix.get():
            suffix = "_clean"
        overwrite = self.pdf_overwrite.get()
        strip_xmp = self.pdf_strip_xmp.get() or strip_all

        def worker() -> None:
            try:
                res = write_pdf_metadata(
                    source,
                    out_dir,
                    rows,
                    suffix=suffix,
                    overwrite=overwrite,
                    overwrite_source=inplace,
                    strip_all=strip_all,
                    strip_xmp=strip_xmp,
                )
            except Exception as exc:
                self.after(0, lambda: self._pdf_write_done(None, str(exc), strip_all))
                return
            self.after(0, lambda: self._pdf_write_done(res, None, strip_all))

        threading.Thread(target=worker, daemon=True).start()

    def _pdf_write_done(
        self, res: WriteResult | None, error: str | None, strip_all: bool
    ) -> None:
        self._set_busy(False)
        if error:
            self.pdf_status.set("Write failed.")
            self.status_var.set("PDF · failed")
            messagebox.showerror(APP_NAME, error)
            return
        assert res is not None
        if not res.success:
            self.pdf_status.set(res.message)
            self.status_var.set("PDF · failed")
            messagebox.showerror(APP_NAME, res.message)
            return

        self.pdf_status.set(res.message)
        self.status_var.set(f"PDF · {res.message}")
        self._log(f"PDF: {res.source.name} → {res.message}")

        if res.output and res.output.is_file():
            if self.pdf_inplace.get():
                self._pdf_load(res.output)
                messagebox.showinfo(APP_NAME, "PDF updated in-place.")
            else:
                if messagebox.askyesno(
                    APP_NAME,
                    f"PDF saved successfully.\n\n{res.output}\n\nOpen output folder?",
                ):
                    self._open_folder(res.output.parent)


def main() -> None:
    app = EXIFexitApp()
    app.mainloop()


if __name__ == "__main__":
    main()
