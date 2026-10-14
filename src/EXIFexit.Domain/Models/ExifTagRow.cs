namespace EXIFexit.Domain.Models;

/// <summary>One editable EXIF/metadata tag row for the studio UI.</summary>
public sealed class ExifTagRow
{
    public string Directory { get; set; } = "";
    public int TagId { get; set; }
    public string Name { get; set; } = "";
    public string Value { get; set; } = "";
    public bool IsEditable { get; set; } = true;

    public string DisplayName => string.IsNullOrWhiteSpace(Name) ? $"Tag{TagId}" : Name;
}
