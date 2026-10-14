# Contributing

Use Windows with a .NET 8-compatible SDK. Keep current application changes in `src`, tests in `tests`, and bundled catalogs in `data`. The Python implementation is retained separately in `legacy/python`.

Before submitting changes, run:

```powershell
dotnet build EXIFexit.sln -c Release
dotnet test EXIFexit.sln -c Release
dotnet list EXIFexit.sln package --vulnerable --include-transitive
.\scripts\check-repository.ps1
```

Generate synthetic image and PDF fixtures inside temporary directories and clean them up after tests. Do not commit personal documents, source photos, private keys, tokens, environment files, logs, or build output. Do not force-add ignored files without reviewing their contents.

Describe behavior changes and any metadata or format limitations. Preserve default copy-based output behavior, and document any changes to it.
