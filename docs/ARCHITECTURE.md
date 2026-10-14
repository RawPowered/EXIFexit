# EXIFexit 2.0 Architecture

## Layers

| Project | Role |
|---------|------|
| `EXIFexit.Domain` | Pure models + `ScrambleEngine` (no I/O) |
| `EXIFexit.Application` | Service interfaces + `JobRunner` use cases |
| `EXIFexit.Infrastructure` | JPEG segment editor, EXIF builder, ImageSharp, PdfPig, PdfSharpCore, mask/locale JSON loaders |
| `EXIFexit.App` | WPF shell, MVVM, DI composition root |

## JPEG strategy

- **Shred:** `JpegSegmentEditor.StripMetadata` removes APP1 (EXIF/XMP), COM, APP13, optional ICC APP2 without re-encoding scan data.
- **Write / scramble:** `ExifBuilder` builds a minimal TIFF/EXIF; `JpegSegmentEditor.UpsertExifApp1` injects APP1 losslessly.

## PDF strategy

- **Read:** UglyToad.PdfPig for Info + page/file facts; XMP presence via byte scan.
- **Write / shred:** PdfSharpCore import + Info rewrite + atomic temp replace.

## Data packs

- `data/masks/core.json` — 64 device masks
- `data/locales/*.json` — UI strings (13 languages)

## Publish

```powershell
.\scripts\publish.ps1
```

Produces self-contained `artifacts/EXIFexit/EXIFexit.exe`.
