namespace EXIFexit.Domain.Models;

public sealed class DeviceMask
{
    public string Id { get; set; } = "";
    public string Label { get; set; } = "";
    public string Category { get; set; } = "";
    public string Region { get; set; } = "";
    public string Country { get; set; } = "";
    public string City { get; set; } = "";
    public string Make { get; set; } = "";
    public string Model { get; set; } = "";
    public string Software { get; set; } = "";
    public string LensMake { get; set; } = "";
    public string LensModel { get; set; } = "";
    public double GpsLat { get; set; }
    public double GpsLon { get; set; }
    public string Creator { get; set; } = "";
    public string Producer { get; set; } = "";
    public string Artist { get; set; } = "";
    public string TimezoneOffset { get; set; } = "+00:00";
    public string LocaleHint { get; set; } = "en_US";
}
