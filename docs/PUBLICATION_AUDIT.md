# Publication audit

Prepared on October 14, 2026 for the initial public source repository.

## Scope and secret checks

- The input directory had no Git repository or prior Git history to publish.
- Gitleaks 8.30.1 was downloaded from its official GitHub release and its archive SHA-256 was checked against the release checksum file.
- The initial directory scan reported no leaks. The staged publication snapshot and initial commit history are scanned again before upload, with output redacted.
- Tracked source paths are checked for credential files, private signing keys, personal media, PDFs, build products, logs, and temporary files.
- A separate source-content review checks for key headers, recognizable tokens, personal email addresses, and machine-specific paths. Bundled device-mask locations and synthetic test coordinates are intentional application data.
- The personal PDF directory, build output, and Python caches are preserved locally and excluded from version control. No personal PDF is used as a test fixture.
- Git uses the GitHub noreply address for RawPowered to avoid publishing the locally configured personal email address.

No credentials or private keys were detected. These checks reduce exposure risk; they cannot guarantee detection of every secret or every form of personal information. Generated executables and personal documents are not included in the publication.

## Organization

- Current .NET app remains in `src`, with tests and data in their existing directories.
- Original Python sources and requirements moved into `legacy/python`; the root batch launcher points to that location.
- Added a full MIT license consistent with the original README, contribution/security guidance, ignore rules, tracked-path checks, and Windows build/test plus Gitleaks automation.
- README now describes PDF rewrite and verification limits, image re-encoding, and the need to keep the published data directory with the executable.

## Validation

- Release solution build: passed.
- Existing unit tests: 4 passed (2 domain, 2 infrastructure), using synthetic data.
- Legacy Python syntax compilation: passed.
- Windows x64 portable publish: passed (self-contained executable with adjacent data packs).
- These checks do not constitute a complete interactive UI or supported-format compatibility test.

## Unresolved dependency advisories

NuGet's audit reports these packages in the resolved dependency graph:

| Package | Version | Scope | Advisory IDs |
| --- | --- | --- | --- |
| SixLabors.ImageSharp | 3.1.12 | App and infrastructure, plus tests | GHSA-gwg2-r3hj-4w44, GHSA-j3p4-wp97-rph4, GHSA-j9gm-c75j-xc9q, GHSA-wmxv-xphr-5c9g, GHSA-jjfr-hcj7-qf5w |
| System.Net.Http | 4.3.0 | Transitive test dependency | GHSA-7jgj-8wvc-jh57 |
| System.Text.RegularExpressions | 4.3.0 | Transitive test dependency | GHSA-cmhx-cq75-c4mj |

ImageSharp 4.1.3 and 3.2.0 were tried during preparation, but each fails the build without a Six Labors license credential. Neither change is included. Keep any future license credentials outside version control. Resolving these findings requires a dependency/licensing decision and further compatibility tests; no advisories were suppressed. Their presence in the dependency graph does not establish that every affected code path is used by this application.

Re-run the dependency audit as advisories evolve:

```powershell
dotnet list EXIFexit.sln package --vulnerable --include-transitive
```

The remaining dependency work is distinct from the credential scan: this repository has no detected embedded credentials, but it is not certified free of software vulnerabilities.
