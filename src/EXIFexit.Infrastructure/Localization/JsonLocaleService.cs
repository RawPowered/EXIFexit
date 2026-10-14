using System.Text.Json;
using EXIFexit.Application.Abstractions;

namespace EXIFexit.Infrastructure.Localization;

public sealed class JsonLocaleService : ILocaleService
{
    private readonly string _localesDir;
    private readonly Dictionary<string, string> _languages;
    private Dictionary<string, string> _strings;
    private Dictionary<string, string> _english;

    public JsonLocaleService(string localesDir)
    {
        _localesDir = localesDir;
        _languages = LoadLanguages();
        _english = LoadCode("en");
        _strings = new Dictionary<string, string>(_english, StringComparer.OrdinalIgnoreCase);
        CurrentCode = "en";
    }

    public IReadOnlyDictionary<string, string> Languages => _languages;
    public string CurrentCode { get; private set; }
    public event EventHandler? LanguageChanged;

    public void SetLanguage(string code)
    {
        if (!_languages.ContainsKey(code))
            code = "en";
        CurrentCode = code;
        var loaded = LoadCode(code);
        // Fall back to English for missing keys
        _strings = new Dictionary<string, string>(_english, StringComparer.OrdinalIgnoreCase);
        foreach (var (k, v) in loaded)
            _strings[k] = v;
        LanguageChanged?.Invoke(this, EventArgs.Empty);
    }

    public string T(string key, string? fallback = null)
    {
        if (_strings.TryGetValue(key, out var v) && !string.IsNullOrEmpty(v))
            return v;
        if (_english.TryGetValue(key, out var e) && !string.IsNullOrEmpty(e))
            return e;
        return fallback ?? key;
    }

    private Dictionary<string, string> LoadLanguages()
    {
        var path = Path.Combine(_localesDir, "languages.json");
        if (!File.Exists(path))
            return new Dictionary<string, string> { ["en"] = "English" };
        using var doc = JsonDocument.Parse(File.ReadAllText(path));
        if (doc.RootElement.TryGetProperty("languages", out var langs))
        {
            return langs.EnumerateObject()
                .ToDictionary(p => p.Name, p => p.Value.GetString() ?? p.Name, StringComparer.OrdinalIgnoreCase);
        }
        return new Dictionary<string, string> { ["en"] = "English" };
    }

    private Dictionary<string, string> LoadCode(string code)
    {
        var path = Path.Combine(_localesDir, $"{code}.json");
        if (!File.Exists(path))
            return new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        var dict = JsonSerializer.Deserialize<Dictionary<string, string>>(File.ReadAllText(path))
                   ?? new Dictionary<string, string>();
        return new Dictionary<string, string>(dict, StringComparer.OrdinalIgnoreCase);
    }
}
