namespace EXIFexit.Domain.Models;

public sealed class OperationResult
{
    public required string SourcePath { get; init; }
    public string? OutputPath { get; init; }
    public bool Success { get; init; }
    public string Message { get; init; } = "";
    public IReadOnlyList<string> TagsRemoved { get; init; } = Array.Empty<string>();
    public bool HadMetadata { get; init; }
    public IReadOnlyList<MetadataFinding> ResidualFindings { get; init; } = Array.Empty<MetadataFinding>();
}

public sealed class MetadataFinding
{
    public string Category { get; init; } = "";
    public string Detail { get; init; } = "";
    public bool IsSensitive { get; init; }
}

public sealed class MetadataDiff
{
    public IReadOnlyList<string> Before { get; init; } = Array.Empty<string>();
    public IReadOnlyList<string> After { get; init; } = Array.Empty<string>();
    public IReadOnlyList<string> Removed => Before.Except(After, StringComparer.OrdinalIgnoreCase).ToList();
    public IReadOnlyList<string> Added => After.Except(Before, StringComparer.OrdinalIgnoreCase).ToList();
    public IReadOnlyList<string> Unchanged => Before.Intersect(After, StringComparer.OrdinalIgnoreCase).ToList();
}

public sealed class QueueItem
{
    public Guid Id { get; } = Guid.NewGuid();
    public required string Path { get; init; }
    public FileKind Kind { get; set; }
    public JobItemStatus Status { get; set; } = JobItemStatus.Pending;
    public string StatusMessage { get; set; } = "";
    public string? OutputPath { get; set; }
    public IReadOnlyList<string> MetadataSummary { get; set; } = Array.Empty<string>();
}

public sealed class OutputOptions
{
    public string OutputDirectory { get; set; } = "";
    public string Suffix { get; set; } = "_clean";
    public bool Overwrite { get; set; }
    public bool OverwriteSourceInPlace { get; set; }
    public bool KeepIcc { get; set; }
    public bool StripXmp { get; set; } = true;
    public bool VerifyAfterWrite { get; set; } = true;
}

public static class SupportedFormats
{
    public static readonly HashSet<string> ImageExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".tif", ".tiff", ".webp", ".bmp", ".gif", ".ico",
    };

    public static readonly HashSet<string> PdfExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".pdf",
    };

    public static readonly HashSet<string> JpegExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".jpg", ".jpeg", ".jpe", ".jfif",
    };

    public static FileKind Classify(string path)
    {
        var ext = Path.GetExtension(path);
        if (ImageExtensions.Contains(ext)) return FileKind.Image;
        if (PdfExtensions.Contains(ext)) return FileKind.Pdf;
        return FileKind.Unsupported;
    }
}
