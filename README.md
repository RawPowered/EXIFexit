# EXIF Exit

EXIF Exit is a Windows desktop tool for inspecting, editing, and removing image and PDF metadata. It also provides PDF file information for troubleshooting and device-mask presets for generating replacement metadata.

The current application is **EXIFexit 2.0**, built with .NET 8 and WPF. The earlier Python application is preserved in [`legacy/python`](legacy/python).

## Features

- **Shred:** queue images and PDFs, remove supported metadata, and inspect residual findings.
- **EXIF Studio:** inspect tags, edit common fields, and replace JPEG EXIF without re-encoding pixels.
- **PDF Studio:** inspect file and page information, view common document Info fields, and rewrite or clear supported metadata.
- **Scramble / Mask:** generate replacement device, location, date, and exposure fields from the bundled device catalog.
- Drag-and-drop, activity logging, and bundled translations.

## Build and run

Requires Windows and the **.NET 8 SDK or a compatible newer SDK**. The published Windows x64 application includes the .NET runtime; Python is only needed for the legacy application.

```powershell
dotnet run --project src/EXIFexit.App -c Release
```

Build a portable application:

```powershell
.\scripts\publish.ps1
.\artifacts\EXIFexit\EXIFexit.exe
```

Keep the generated `data` directory beside the executable; it contains the translations and device masks. Build output is excluded from Git.

## Privacy and format limits

- Processing is local; the application has no telemetry or network service integration.
- The default output settings create copies. In-place overwrite is an explicit option.
- JPEG shredding removes EXIF/XMP APP1, comments, and IPTC APP13 without re-encoding image pixels. ICC retention is optional.
- Other image formats are decoded and saved again. Review image quality, color, animation, and format support before replacing originals.
- Editing or scrambling metadata does not prove anonymity. Existing metadata outside the edited fields may remain. Verification checks selected metadata fields, not every possible data channel.
- PDF cleanup rebuilds pages and clears supported document Info fields. It is **not a complete PDF sanitization or redaction tool**. The writer may add producer/date fields, and the XMP check only scans for an uncompressed namespace marker.
- PDF rewriting can change or discard document-level features and invalidate signatures. Work from copies, particularly when debugging signed PDFs.
- Visible content, filenames, filesystem timestamps, and information embedded in image pixels or page content require separate review.

## Dependency status

The current ImageSharp 3.1.12 dependency has known NuGet security advisories. Newer versions tested during preparation require a Six Labors license credential, so the existing working version is retained. See [the publication audit](docs/PUBLICATION_AUDIT.md) for the unresolved dependency work.

## Repository layout

```text
src/                 .NET domain, application, infrastructure, and WPF UI
data/               Device-mask and translation packs
tests/              Synthetic-data unit tests
scripts/            Build and privacy-check helpers
docs/               Architecture and publication audit
legacy/python/      Earlier Python implementation and its dependencies
.github/workflows/  Windows build, tests, and secret scanning
```

## Validation

```powershell
dotnet test EXIFexit.sln -c Release
dotnet list EXIFexit.sln package --vulnerable --include-transitive
.\scripts\check-repository.ps1
```

The repository check requires [Gitleaks](https://github.com/gitleaks/gitleaks) on PATH. It checks tracked paths for private material and scans the committed history. Run it before pushing.

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidance and [SECURITY.md](SECURITY.md) for reporting vulnerabilities. Personal documents, local logs, credentials, and generated binaries belong outside version control. Tests should generate their own sample images and PDFs.

## License

Project source is licensed under the [MIT License](LICENSE), consistent with the original README. Dependencies retain their own licenses; review those terms before redistributing binaries.
