using EXIFexit.Application.Abstractions;
using EXIFexit.Domain.Models;
using EXIFexit.Infrastructure.Paths;
using MetadataExtractor;
using MetadataExtractor.Formats.Exif;
using MetadataExtractor.Formats.Xmp;
using SixLabors.ImageSharp;
using SixLabors.ImageSharp.Formats.Jpeg;
using SixLabors.ImageSharp.Formats.Png;
using SixLabors.ImageSharp.Metadata.Profiles.Exif;
using SixLabors.ImageSharp.Processing;
using Directory = System.IO.Directory;

namespace EXIFexit.Infrastructure.Imaging;

public sealed class ImageMetadataService : IImageMetadataService
{
    private readonly IPathPolicy _paths;

    public ImageMetadataService(IPathPolicy paths) => _paths = paths;

    public IReadOnlyList<string> InspectSummary(string path)
    {
        var tags = new List<string>();
        try
        {
            var directories = ImageMetadataReader.ReadMetadata(path);
            foreach (var dir in directories)
            {
                var count = dir.Tags.Count;
                if (count == 0) continue;
                var name = dir.Name;
                if (name.Contains("GPS", StringComparison.OrdinalIgnoreCase))
                    tags.Add($"GPS ({count} tags)");
                else if (name.Contains("Exif", StringComparison.OrdinalIgnoreCase))
                    tags.Add($"{name} ({count})");
                else if (dir is XmpDirectory)
                    tags.Add("XMP");
                else if (count > 0 && !name.Contains("File", StringComparison.OrdinalIgnoreCase)
                                   && !name.Contains("JPEG", StringComparison.OrdinalIgnoreCase))
                    tags.Add($"{name} ({count})");
            }
        }
        catch (Exception ex)
        {
            tags.Add($"(could not inspect: {ex.Message})");
        }
        return tags;
    }

    public IReadOnlyList<ExifTagRow> LoadTags(string path)
    {
        var rows = new List<ExifTagRow>();
        try
        {
            var directories = ImageMetadataReader.ReadMetadata(path);
            foreach (var dir in directories)
            {
                if (dir.Name.Contains("File Type", StringComparison.OrdinalIgnoreCase) ||
                    dir.Name.Equals("File", StringComparison.OrdinalIgnoreCase))
                    continue;

                foreach (var tag in dir.Tags)
                {
                    rows.Add(new ExifTagRow
                    {
                        Directory = dir.Name,
                        TagId = tag.Type,
                        Name = tag.Name,
                        Value = tag.Description ?? "",
                        IsEditable = IsLikelyEditable(dir.Name),
                    });
                }
            }
        }
        catch
        {
            // return empty
        }
        return rows;
    }

    public IReadOnlyList<MetadataFinding> Verify(string path)
    {
        var findings = new List<MetadataFinding>();
        try
        {
            var directories = ImageMetadataReader.ReadMetadata(path);
            foreach (var dir in directories)
            {
                if (dir is GpsDirectory gps && gps.Tags.Count > 0)
                {
                    findings.Add(new MetadataFinding
                    {
                        Category = "GPS",
                        Detail = $"{gps.Tags.Count} GPS tag(s) remain",
                        IsSensitive = true,
                    });
                }
                if (dir is XmpDirectory)
                {
                    findings.Add(new MetadataFinding
                    {
                        Category = "XMP",
                        Detail = "XMP packet present",
                        IsSensitive = true,
                    });
                }
                if (dir is ExifIfd0Directory or ExifSubIfdDirectory)
                {
                    var interesting = dir.Tags
                        .Where(t => t.Name is "Make" or "Model" or "Software" or "Artist" or "Copyright"
                            or "Date/Time" or "Date/Time Original")
                        .ToList();
                    foreach (var t in interesting)
                    {
                        findings.Add(new MetadataFinding
                        {
                            Category = "EXIF",
                            Detail = $"{t.Name}={t.Description}",
                            IsSensitive = t.Name is "Artist" or "Copyright" or "Make" or "Model",
                        });
                    }
                }
            }
        }
        catch (Exception ex)
        {
            findings.Add(new MetadataFinding
            {
                Category = "Error",
                Detail = ex.Message,
                IsSensitive = false,
            });
        }
        return findings;
    }

    public async Task<OperationResult> ShredAsync(string sourcePath, OutputOptions options, CancellationToken ct = default)
    {
        try
        {
            ct.ThrowIfCancellationRequested();
            if (!File.Exists(sourcePath))
                return Fail(sourcePath, "Source file not found");

            var before = InspectSummary(sourcePath);
            var ext = Path.GetExtension(sourcePath);
            string outPath;
            if (options.OverwriteSourceInPlace)
                outPath = sourcePath;
            else
            {
                var outDir = string.IsNullOrWhiteSpace(options.OutputDirectory)
                    ? Path.GetDirectoryName(sourcePath) ?? "."
                    : options.OutputDirectory;
                outPath = _paths.ResolveOutputPath(sourcePath, outDir, options.Suffix, options.Overwrite);
            }

            if (SupportedFormats.JpegExtensions.Contains(ext))
            {
                var bytes = await File.ReadAllBytesAsync(sourcePath, ct).ConfigureAwait(false);
                var clean = JpegSegmentEditor.StripMetadata(bytes, options.KeepIcc);
                await PathPolicy.AtomicWriteAsync(outPath, async tmp =>
                {
                    await File.WriteAllBytesAsync(tmp, clean, ct).ConfigureAwait(false);
                }).ConfigureAwait(false);
            }
            else
            {
                await PathPolicy.AtomicWriteAsync(outPath, async tmp =>
                {
                    using var image = await Image.LoadAsync(sourcePath, ct).ConfigureAwait(false);
                    // Drop all profiles
                    image.Metadata.ExifProfile = null;
                    image.Metadata.IccProfile = options.KeepIcc ? image.Metadata.IccProfile : null;
                    image.Metadata.XmpProfile = null;
                    image.Metadata.IptcProfile = null;

                    await image.SaveAsync(tmp, ct).ConfigureAwait(false);
                }).ConfigureAwait(false);
            }

            var residual = options.VerifyAfterWrite ? Verify(outPath) : Array.Empty<MetadataFinding>();
            return new OperationResult
            {
                SourcePath = sourcePath,
                OutputPath = outPath,
                Success = true,
                HadMetadata = before.Count > 0,
                TagsRemoved = before,
                ResidualFindings = residual,
                Message = before.Count > 0
                    ? $"Stripped {before.Count} metadata group(s) → {Path.GetFileName(outPath)}"
                    : $"No metadata found; saved clean copy → {Path.GetFileName(outPath)}",
            };
        }
        catch (Exception ex)
        {
            return Fail(sourcePath, ex.Message);
        }
    }

    public async Task<OperationResult> WriteExifAsync(
        string sourcePath,
        IReadOnlyList<ExifTagRow> tags,
        OutputOptions options,
        CancellationToken ct = default)
    {
        var fields = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var t in tags)
        {
            if (string.IsNullOrWhiteSpace(t.Name) || string.IsNullOrWhiteSpace(t.Value))
                continue;
            // Prefer short common names
            var key = NormalizeTagName(t.Name);
            fields[key] = t.Value;
        }
        return await WriteQuickFieldsAsync(sourcePath, fields, options, ct).ConfigureAwait(false);
    }

    public async Task<OperationResult> WriteQuickFieldsAsync(
        string sourcePath,
        IReadOnlyDictionary<string, string> fields,
        OutputOptions options,
        CancellationToken ct = default)
    {
        try
        {
            ct.ThrowIfCancellationRequested();
            if (!File.Exists(sourcePath))
                return Fail(sourcePath, "Source file not found");

            var ext = Path.GetExtension(sourcePath);
            string outPath;
            if (options.OverwriteSourceInPlace)
                outPath = sourcePath;
            else
            {
                var outDir = string.IsNullOrWhiteSpace(options.OutputDirectory)
                    ? Path.GetDirectoryName(sourcePath) ?? "."
                    : options.OutputDirectory;
                var suffix = string.IsNullOrEmpty(options.Suffix) ? "_edited" : options.Suffix;
                outPath = _paths.ResolveOutputPath(sourcePath, outDir, suffix, options.Overwrite);
            }

            if (SupportedFormats.JpegExtensions.Contains(ext))
            {
                var bytes = await File.ReadAllBytesAsync(sourcePath, ct).ConfigureAwait(false);
                // Start from stripped base then inject new EXIF for clean rewrite semantics
                // For scramble/edit we want to keep image data: replace EXIF APP1 only
                var app1 = ExifBuilder.BuildApp1Payload(fields);
                var updated = JpegSegmentEditor.UpsertExifApp1(bytes, app1);
                await PathPolicy.AtomicWriteAsync(outPath, async tmp =>
                {
                    await File.WriteAllBytesAsync(tmp, updated, ct).ConfigureAwait(false);
                }).ConfigureAwait(false);
            }
            else
            {
                await PathPolicy.AtomicWriteAsync(outPath, async tmp =>
                {
                    using var image = await Image.LoadAsync(sourcePath, ct).ConfigureAwait(false);
                    var profile = image.Metadata.ExifProfile ?? new ExifProfile();
                    ApplyImageSharpExif(profile, fields);
                    image.Metadata.ExifProfile = profile;
                    await image.SaveAsync(tmp, ct).ConfigureAwait(false);
                }).ConfigureAwait(false);
            }

            return new OperationResult
            {
                SourcePath = sourcePath,
                OutputPath = outPath,
                Success = true,
                Message = $"Wrote {fields.Count} field(s) → {Path.GetFileName(outPath)}",
            };
        }
        catch (Exception ex)
        {
            return Fail(sourcePath, ex.Message);
        }
    }

    private static void ApplyImageSharpExif(ExifProfile profile, IReadOnlyDictionary<string, string> fields)
    {
        foreach (var (key, value) in fields)
        {
            if (string.IsNullOrWhiteSpace(value)) continue;
            switch (key.ToLowerInvariant())
            {
                case "make": profile.SetValue(ExifTag.Make, value); break;
                case "model": profile.SetValue(ExifTag.Model, value); break;
                case "software": profile.SetValue(ExifTag.Software, value); break;
                case "artist": profile.SetValue(ExifTag.Artist, value); break;
                case "copyright": profile.SetValue(ExifTag.Copyright, value); break;
                case "imagedescription": profile.SetValue(ExifTag.ImageDescription, value); break;
                case "datetime": profile.SetValue(ExifTag.DateTime, value); break;
                case "datetimeoriginal": profile.SetValue(ExifTag.DateTimeOriginal, value); break;
                case "datetimedigitized": profile.SetValue(ExifTag.DateTimeDigitized, value); break;
                case "lensmodel": profile.SetValue(ExifTag.LensModel, value); break;
                case "lensmake": profile.SetValue(ExifTag.LensMake, value); break;
                case "usercomment": profile.SetValue(ExifTag.UserComment, value); break;
            }
        }
    }

    private static string NormalizeTagName(string name)
    {
        // MetadataExtractor uses "Date/Time Original" etc.
        return name
            .Replace("Date/Time Original", "DateTimeOriginal", StringComparison.OrdinalIgnoreCase)
            .Replace("Date/Time Digitized", "DateTimeDigitized", StringComparison.OrdinalIgnoreCase)
            .Replace("Date/Time", "DateTime", StringComparison.OrdinalIgnoreCase)
            .Replace(" ", "")
            .Replace("/", "");
    }

    private static bool IsLikelyEditable(string directoryName) =>
        directoryName.Contains("Exif", StringComparison.OrdinalIgnoreCase)
        || directoryName.Contains("GPS", StringComparison.OrdinalIgnoreCase)
        || directoryName.Contains("IPTC", StringComparison.OrdinalIgnoreCase);

    private static OperationResult Fail(string source, string message) => new()
    {
        SourcePath = source,
        Success = false,
        Message = message,
    };
}
