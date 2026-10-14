namespace EXIFexit.Domain.Models;

public sealed class PdfMetaRow
{
    public string Key { get; set; } = "";
    public string Value { get; set; } = "";
    public bool IsEditable { get; set; } = true;
    public bool IsStandard { get; set; }
}
