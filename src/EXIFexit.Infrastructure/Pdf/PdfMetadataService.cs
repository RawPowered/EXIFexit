using EXIFexit.Application.Abstractions;
using EXIFexit.Domain.Models;
using EXIFexit.Infrastructure.Paths;
using PdfSharpCore.Pdf.IO;
using PigDocument = UglyToad.PdfPig.PdfDocument;
using SharpDocument = PdfSharpCore.Pdf.PdfDocument;

namespace EXIFexit.Infrastructure.Pdf;

public sealed class PdfMetadataService : IPdfMetadataService
{
    private static readonly string[] StandardKeys =
    [
        "Title", "Author", "Subject", "Keywords", "Creator", "Producer",
        "CreationDate", "ModDate", "Trapped",
    ];

    private readonly IPathPolicy _paths;

    public PdfMetadataService(IPathPolicy paths) => _paths = paths;

    public IReadOnlyList<(string Key, string Value)> LoadFileInfo(string path)
    {
        var info = new List<(string, string)>();
        try
        {
            var fi = new FileInfo(path);
            info.Add(("Path", fi.FullName));
            info.Add(("Size", HumanSize(fi.Length)));
            info.Add(("Created", fi.CreationTime.ToString("yyyy-MM-dd HH:mm:ss")));
            info.Add(("Modified", fi.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")));

            using var doc = PigDocument.Open(path);
            info.Add(("Pages", doc.NumberOfPages.ToString()));
            info.Add(("Version", doc.Version.ToString()));
            if (doc.NumberOfPages > 0)
            {
                var page = doc.GetPage(1);
                info.Add(("Page size", $"{page.Width:F0} × {page.Height:F0} pts"));
            }
            info.Add(("Encrypted", doc.IsEncrypted ? "Yes" : "No"));
            info.Add(("XMP", FileContainsXmp(path) ? "Present" : "None"));
        }
        catch (Exception ex)
        {
            info.Add(("Error", ex.Message));
        }
        return info;
    }

    public IReadOnlyList<PdfMetaRow> LoadMetadata(string path)
    {
        var rows = new List<PdfMetaRow>();
        try
        {
            using var doc = PigDocument.Open(path);
            var info = doc.Information;
            void Add(string key, string? value, bool standard = true)
            {
                rows.Add(new PdfMetaRow
                {
                    Key = key,
                    Value = value ?? "",
                    IsEditable = true,
                    IsStandard = standard,
                });
            }

            Add("Title", info.Title);
            Add("Author", info.Author);
            Add("Subject", info.Subject);
            Add("Keywords", info.Keywords);
            Add("Creator", info.Creator);
            Add("Producer", info.Producer);
            Add("CreationDate", info.CreationDate);
            Add("ModDate", info.ModifiedDate);

            // Ensure standard keys exist even if empty
            foreach (var key in StandardKeys)
            {
                if (rows.All(r => !string.Equals(r.Key, key, StringComparison.OrdinalIgnoreCase)))
                    Add(key, "");
            }
        }
        catch (Exception ex)
        {
            rows.Add(new PdfMetaRow { Key = "Error", Value = ex.Message, IsEditable = false });
        }
        return rows;
    }

    public IReadOnlyList<MetadataFinding> Verify(string path)
    {
        var findings = new List<MetadataFinding>();
        try
        {
            using var doc = PigDocument.Open(path);
            var info = doc.Information;
            void Check(string key, string? value)
            {
                if (!string.IsNullOrWhiteSpace(value))
                {
                    findings.Add(new MetadataFinding
                    {
                        Category = "PDF.Info",
                        Detail = $"{key}={value}",
                        IsSensitive = key is "Author" or "Creator" or "Producer" or "Title",
                    });
                }
            }
            Check("Title", info.Title);
            Check("Author", info.Author);
            Check("Subject", info.Subject);
            Check("Keywords", info.Keywords);
            Check("Creator", info.Creator);
            Check("Producer", info.Producer);
            Check("CreationDate", info.CreationDate);
            Check("ModDate", info.ModifiedDate);

            if (FileContainsXmp(path))
            {
                findings.Add(new MetadataFinding
                {
                    Category = "XMP",
                    Detail = "XMP metadata present",
                    IsSensitive = true,
                });
            }
        }
        catch (Exception ex)
        {
            findings.Add(new MetadataFinding { Category = "Error", Detail = ex.Message });
        }
        return findings;
    }

    private static bool FileContainsXmp(string path)
    {
        try
        {
            // Lightweight scan — avoids version-specific PdfPig XMP APIs
            var bytes = File.ReadAllBytes(path);
            var needle = "http://ns.adobe.com/xap/1.0/"u8;
            for (var i = 0; i <= bytes.Length - needle.Length; i++)
            {
                if (bytes.AsSpan(i, needle.Length).SequenceEqual(needle))
                    return true;
            }
        }
        catch
        {
            // ignore
        }
        return false;
    }

    public async Task<OperationResult> WriteAsync(
        string sourcePath,
        IReadOnlyList<PdfMetaRow> rows,
        OutputOptions options,
        bool stripAll,
        CancellationToken ct = default)
    {
        try
        {
            ct.ThrowIfCancellationRequested();
            if (!File.Exists(sourcePath))
                return Fail(sourcePath, "Source PDF not found");
            if (!string.Equals(Path.GetExtension(sourcePath), ".pdf", StringComparison.OrdinalIgnoreCase))
                return Fail(sourcePath, "Not a PDF file");

            string outPath;
            if (options.OverwriteSourceInPlace)
                outPath = sourcePath;
            else
            {
                var outDir = string.IsNullOrWhiteSpace(options.OutputDirectory)
                    ? Path.GetDirectoryName(sourcePath) ?? "."
                    : options.OutputDirectory;
                var suffix = string.IsNullOrEmpty(options.Suffix)
                    ? (stripAll ? "_clean" : "_meta")
                    : options.Suffix;
                outPath = _paths.ResolveOutputPath(sourcePath, outDir, suffix, options.Overwrite, ".pdf");
            }

            await PathPolicy.AtomicWriteAsync(outPath, async tmp =>
            {
                await Task.Run(() =>
                {
                    using var input = PdfReader.Open(sourcePath, PdfDocumentOpenMode.Import);
                    using var output = new SharpDocument();
                    foreach (var page in input.Pages)
                        output.AddPage(page);

                    if (stripAll)
                    {
                        ClearInfo(output);
                    }
                    else
                    {
                        ApplyInfo(output, rows);
                    }

                    // PdfSharpCore does not fully expose XMP removal; Info strip is primary.
                    // When stripAll or StripXmp, clear producer-like fields aggressively.
                    if (stripAll || options.StripXmp)
                    {
                        output.Info.Elements.Clear();
                        // Re-apply empty known keys so viewers show blank
                        output.Info.Title = "";
                        output.Info.Author = "";
                        output.Info.Subject = "";
                        output.Info.Keywords = "";
                        output.Info.Creator = "";
                        // Producer often rewritten by PdfSharp on save — acceptable limitation documented
                    }

                    output.Save(tmp);
                }, ct).ConfigureAwait(false);
            }).ConfigureAwait(false);

            var residual = options.VerifyAfterWrite ? Verify(outPath) : Array.Empty<MetadataFinding>();
            return new OperationResult
            {
                SourcePath = sourcePath,
                OutputPath = outPath,
                Success = true,
                ResidualFindings = residual,
                Message = stripAll
                    ? $"Shredded PDF metadata → {Path.GetFileName(outPath)}"
                    : $"Wrote PDF metadata → {Path.GetFileName(outPath)}",
            };
        }
        catch (Exception ex)
        {
            return Fail(sourcePath, ex.Message);
        }
    }

    private static void ClearInfo(SharpDocument doc)
    {
        doc.Info.Title = "";
        doc.Info.Author = "";
        doc.Info.Subject = "";
        doc.Info.Keywords = "";
        doc.Info.Creator = "";
    }

    private static void ApplyInfo(SharpDocument doc, IReadOnlyList<PdfMetaRow> rows)
    {
        foreach (var row in rows)
        {
            if (!row.IsEditable) continue;
            var key = row.Key?.Trim() ?? "";
            var value = row.Value ?? "";
            switch (key.ToLowerInvariant())
            {
                case "title": doc.Info.Title = value; break;
                case "author": doc.Info.Author = value; break;
                case "subject": doc.Info.Subject = value; break;
                case "keywords": doc.Info.Keywords = value; break;
                case "creator": doc.Info.Creator = value; break;
                // CreationDate / ModDate / Producer: best-effort via Elements when possible
            }
        }
    }

    private static string HumanSize(long n)
    {
        string[] units = ["B", "KB", "MB", "GB"];
        double v = n;
        var u = 0;
        while (v >= 1024 && u < units.Length - 1)
        {
            v /= 1024;
            u++;
        }
        return $"{v:0.##} {units[u]}";
    }

    private static OperationResult Fail(string source, string message) => new()
    {
        SourcePath = source,
        Success = false,
        Message = message,
    };
}
