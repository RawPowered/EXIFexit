namespace EXIFexit.Domain.Models;

public sealed class ScramblePayload
{
    public required DeviceMask Mask { get; init; }
    public Dictionary<string, string> ExifFields { get; init; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, string> PdfFields { get; init; } = new(StringComparer.OrdinalIgnoreCase);
    public string Summary { get; init; } = "";
}
