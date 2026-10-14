using System.Text.Json;
using System.Text.Json.Serialization;
using EXIFexit.Application.Abstractions;
using EXIFexit.Domain.Models;

namespace EXIFexit.Infrastructure.Masks;

public sealed class JsonMaskCatalog : IMaskCatalog
{
    private readonly List<DeviceMask> _masks;
    private readonly List<string> _categories;
    private readonly Dictionary<string, string> _regionLabels;

    public JsonMaskCatalog(string jsonPath)
    {
        if (!File.Exists(jsonPath))
            throw new FileNotFoundException("Mask pack not found", jsonPath);

        var json = File.ReadAllText(jsonPath);
        var pack = JsonSerializer.Deserialize<MaskPackDto>(json, new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true,
        }) ?? throw new InvalidDataException("Invalid mask pack JSON");

        _masks = pack.Masks.Select(m => new DeviceMask
        {
            Id = m.Id ?? "",
            Label = m.Label ?? "",
            Category = m.Category ?? "",
            Region = m.Region ?? "",
            Country = m.Country ?? "",
            City = m.City ?? "",
            Make = m.Make ?? "",
            Model = m.Model ?? "",
            Software = m.Software ?? "",
            LensMake = m.LensMake ?? "",
            LensModel = m.LensModel ?? "",
            GpsLat = m.GpsLat,
            GpsLon = m.GpsLon,
            Creator = m.Creator ?? "",
            Producer = m.Producer ?? "",
            Artist = m.Artist ?? "",
            TimezoneOffset = m.TimezoneOffset ?? "+00:00",
            LocaleHint = m.LocaleHint ?? "en_US",
        }).ToList();

        _categories = pack.Categories?.ToList()
                      ?? _masks.Select(m => m.Category).Distinct(StringComparer.OrdinalIgnoreCase).OrderBy(x => x).ToList();
        _regionLabels = pack.RegionLabels ?? new Dictionary<string, string>();
    }

    public IReadOnlyList<DeviceMask> All => _masks;
    public IReadOnlyList<string> Categories => _categories;
    public IReadOnlyDictionary<string, string> RegionLabels => _regionLabels;

    public DeviceMask? GetById(string id) =>
        _masks.FirstOrDefault(m => string.Equals(m.Id, id, StringComparison.OrdinalIgnoreCase));

    public IReadOnlyList<DeviceMask> Filter(string? category, string? region)
    {
        IEnumerable<DeviceMask> q = _masks;
        if (!string.IsNullOrWhiteSpace(category) &&
            !string.Equals(category, "all", StringComparison.OrdinalIgnoreCase))
            q = q.Where(m => string.Equals(m.Category, category, StringComparison.OrdinalIgnoreCase));
        if (!string.IsNullOrWhiteSpace(region) &&
            !string.Equals(region, "all", StringComparison.OrdinalIgnoreCase))
            q = q.Where(m => string.Equals(m.Region, region, StringComparison.OrdinalIgnoreCase));
        return q.ToList();
    }

    public DeviceMask PickRandom(string? category, string? region, Random? rng = null)
    {
        rng ??= Random.Shared;
        var list = Filter(category, region);
        if (list.Count == 0)
            list = _masks;
        if (list.Count == 0)
            throw new InvalidOperationException("No device masks loaded");
        return list[rng.Next(list.Count)];
    }

    private sealed class MaskPackDto
    {
        public int Version { get; set; }
        public List<string>? Categories { get; set; }
        public Dictionary<string, string>? RegionLabels { get; set; }
        public List<MaskDto> Masks { get; set; } = new();
    }

    private sealed class MaskDto
    {
        public string? Id { get; set; }
        public string? Label { get; set; }
        public string? Category { get; set; }
        public string? Region { get; set; }
        public string? Country { get; set; }
        public string? City { get; set; }
        public string? Make { get; set; }
        public string? Model { get; set; }
        public string? Software { get; set; }
        public string? LensMake { get; set; }
        public string? LensModel { get; set; }
        public double GpsLat { get; set; }
        public double GpsLon { get; set; }
        public string? Creator { get; set; }
        public string? Producer { get; set; }
        public string? Artist { get; set; }
        public string? TimezoneOffset { get; set; }
        public string? LocaleHint { get; set; }
    }
}
