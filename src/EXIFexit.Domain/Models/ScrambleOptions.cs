namespace EXIFexit.Domain.Models;

public sealed class ScrambleOptions
{
    public bool RandomizeGps { get; set; } = true;
    public double GpsJitterKm { get; set; } = 3.0;
    public bool RandomizeDateTime { get; set; } = true;
    public int DaysBackMin { get; set; } = 1;
    public int DaysBackMax { get; set; } = 400;
    public bool RandomizeExposure { get; set; } = true;
    public bool SetArtist { get; set; }
    public string ArtistName { get; set; } = "";
    public string UserComment { get; set; } = "";
    public string PdfTitle { get; set; } = "";
    public string PdfSubject { get; set; } = "";
    public string PdfKeywords { get; set; } = "";
    public string PdfAuthor { get; set; } = "";
}
