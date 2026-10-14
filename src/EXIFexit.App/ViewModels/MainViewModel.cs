using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.Windows;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using EXIFexit.Application.Abstractions;
using EXIFexit.Domain.Models;
using EXIFexit.Domain.Scramble;
using Microsoft.Win32;

namespace EXIFexit.App;

public partial class MainViewModel : ObservableObject
{
    private readonly IImageMetadataService _images;
    private readonly IPdfMetadataService _pdfs;
    private readonly IMaskCatalog _masks;
    private readonly IJobRunner _jobs;
    private readonly ILocaleService _locale;
    private CancellationTokenSource? _cts;

    public MainViewModel(
        IImageMetadataService images,
        IPdfMetadataService pdfs,
        IMaskCatalog masks,
        IJobRunner jobs,
        ILocaleService locale)
    {
        _images = images;
        _pdfs = pdfs;
        _masks = masks;
        _jobs = jobs;
        _locale = locale;

        Queue = new ObservableCollection<QueueItemVm>();
        LogLines = new ObservableCollection<string>();
        ExifRows = new ObservableCollection<ExifTagRow>();
        PdfRows = new ObservableCollection<PdfMetaRow>();
        PdfFileInfo = new ObservableCollection<KeyValueItem>();
        MaskLabels = new ObservableCollection<string>();
        CategoryOptions = new ObservableCollection<string>(new[] { "all" }.Concat(_masks.Categories));
        RegionOptions = new ObservableCollection<string>(
            new[] { "all" }.Concat(_masks.All.Select(m => m.Region).Distinct().OrderBy(x => x)));
        LanguageOptions = new ObservableCollection<string>(_locale.Languages.Values);
        LanguageCodeByDisplay = _locale.Languages.ToDictionary(kv => kv.Value, kv => kv.Key);

        OutputDirectory = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.MyPictures), "EXIFexit");
        StudioOutputDirectory = OutputDirectory;
        PdfOutputDirectory = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "EXIFexit");

        SelectedCategory = "all";
        SelectedRegion = "all";
        SelectedLanguageDisplay = _locale.Languages.TryGetValue("en", out var en) ? en : "English";
        RefreshMasks();
        StatusText = "Ready. Drop files or add images/PDFs to the queue.";
        Log("EXIFexit 2.0 ready — offline, no network, originals safe by default.");
    }

    public ObservableCollection<QueueItemVm> Queue { get; }
    public ObservableCollection<string> LogLines { get; }
    public ObservableCollection<ExifTagRow> ExifRows { get; }
    public ObservableCollection<PdfMetaRow> PdfRows { get; }
    public ObservableCollection<KeyValueItem> PdfFileInfo { get; }
    public ObservableCollection<string> MaskLabels { get; }
    public ObservableCollection<string> CategoryOptions { get; }
    public ObservableCollection<string> RegionOptions { get; }
    public ObservableCollection<string> LanguageOptions { get; }
    private Dictionary<string, string> LanguageCodeByDisplay { get; }
    private Dictionary<string, string> MaskIdByLabel { get; } = new();

    [ObservableProperty] private string _statusText = "";
    [ObservableProperty] private string _outputDirectory = "";
    [ObservableProperty] private string _suffix = "_clean";
    [ObservableProperty] private bool _keepIcc;
    [ObservableProperty] private bool _overwrite;
    [ObservableProperty] private bool _overwriteInPlace;
    [ObservableProperty] private bool _recursiveFolders;
    [ObservableProperty] private bool _verifyAfter = true;
    [ObservableProperty] private double _progress;
    [ObservableProperty] private bool _isBusy;
    [ObservableProperty] private QueueItemVm? _selectedQueueItem;

    [ObservableProperty] private string _studioPath = "";
    [ObservableProperty] private string _studioOutputDirectory = "";
    [ObservableProperty] private string _studioSuffix = "_edited";
    [ObservableProperty] private string _studioStatus = "Open an image to edit EXIF.";
    [ObservableProperty] private string _quickMake = "";
    [ObservableProperty] private string _quickModel = "";
    [ObservableProperty] private string _quickSoftware = "";
    [ObservableProperty] private string _quickArtist = "";
    [ObservableProperty] private string _quickDateTime = "";
    [ObservableProperty] private string _quickGpsLat = "";
    [ObservableProperty] private string _quickGpsLon = "";

    [ObservableProperty] private string _pdfPath = "";
    [ObservableProperty] private string _pdfOutputDirectory = "";
    [ObservableProperty] private string _pdfSuffix = "_meta";
    [ObservableProperty] private string _pdfStatus = "Open a PDF to inspect metadata.";
    [ObservableProperty] private bool _pdfStripXmp = true;

    [ObservableProperty] private string _selectedCategory = "all";
    [ObservableProperty] private string _selectedRegion = "all";
    [ObservableProperty] private string _selectedMaskLabel = "";
    [ObservableProperty] private string _maskCountText = "";
    [ObservableProperty] private string _scrambleStatus = "Pick a device mask, then preview or apply.";
    [ObservableProperty] private string _scramblePreview = "";
    [ObservableProperty] private bool _scrambleGps = true;
    [ObservableProperty] private bool _scrambleDates = true;
    [ObservableProperty] private bool _scrambleExposure = true;
    [ObservableProperty] private string _scrambleArtist = "";
    [ObservableProperty] private string _scrambleComment = "";
    [ObservableProperty] private string _scrambleBatchSuffix = "_masked";
    [ObservableProperty] private string _selectedLanguageDisplay = "English";
    [ObservableProperty] private string _verifyReport = "";
    [ObservableProperty] private string _diffReport = "";

    private ScramblePayload? _lastPayload;

    partial void OnSelectedCategoryChanged(string value) => RefreshMasks();
    partial void OnSelectedRegionChanged(string value) => RefreshMasks();

    partial void OnSelectedLanguageDisplayChanged(string value)
    {
        if (LanguageCodeByDisplay.TryGetValue(value, out var code))
            _locale.SetLanguage(code);
    }

    partial void OnSelectedQueueItemChanged(QueueItemVm? value)
    {
        if (value == null) return;
        if (value.Kind == FileKind.Image)
        {
            StudioPath = value.Path;
            LoadStudioFromPath(value.Path);
        }
        else if (value.Kind == FileKind.Pdf)
        {
            PdfPath = value.Path;
            LoadPdfFromPath(value.Path);
        }
    }

    [RelayCommand]
    private void AddFiles()
    {
        var dlg = new OpenFileDialog
        {
            Multiselect = true,
            Filter = "Images & PDF|*.jpg;*.jpeg;*.jpe;*.jfif;*.png;*.tif;*.tiff;*.webp;*.bmp;*.gif;*.ico;*.pdf|All files|*.*",
        };
        if (dlg.ShowDialog() == true)
            AddPaths(dlg.FileNames);
    }

    [RelayCommand]
    private void AddFolder()
    {
        var dlg = new OpenFolderDialog { Title = "Add folder" };
        if (dlg.ShowDialog() != true) return;
        var option = RecursiveFolders ? SearchOption.AllDirectories : SearchOption.TopDirectoryOnly;
        var files = Directory.EnumerateFiles(dlg.FolderName, "*.*", option)
            .Where(f => SupportedFormats.Classify(f) != FileKind.Unsupported);
        AddPaths(files);
    }

    [RelayCommand]
    private void ClearQueue()
    {
        Queue.Clear();
        StatusText = "Queue cleared.";
    }

    [RelayCommand]
    private void RemoveSelected()
    {
        if (SelectedQueueItem != null)
            Queue.Remove(SelectedQueueItem);
    }

    public void AddPaths(IEnumerable<string> paths)
    {
        var added = 0;
        foreach (var path in paths.Select(Path.GetFullPath).Distinct(StringComparer.OrdinalIgnoreCase))
        {
            if (!File.Exists(path)) continue;
            var kind = SupportedFormats.Classify(path);
            if (kind == FileKind.Unsupported) continue;
            if (Queue.Any(q => string.Equals(q.Path, path, StringComparison.OrdinalIgnoreCase)))
                continue;

            var summary = kind == FileKind.Image
                ? _images.InspectSummary(path)
                : _pdfs.LoadMetadata(path).Where(r => !string.IsNullOrWhiteSpace(r.Value)).Select(r => $"{r.Key}").Take(8).ToList();

            Queue.Add(new QueueItemVm
            {
                Path = path,
                Kind = kind,
                DisplayName = Path.GetFileName(path),
                MetaSummary = string.Join(" · ", summary),
                Status = JobItemStatus.Pending,
            });
            added++;
        }
        StatusText = added > 0 ? $"Added {added} file(s). Queue: {Queue.Count}" : "No new supported files.";
        if (added > 0) Log($"Queued +{added} (total {Queue.Count})");
    }

    [RelayCommand]
    private async Task ShredQueueAsync()
    {
        if (IsBusy || Queue.Count == 0) return;
        var sources = Queue.Select(q => q.Path).ToList();
        var options = BuildOutputOptions(OutputDirectory, Suffix);
        await RunJobAsync(async ct =>
        {
            var progress = new Progress<JobProgress>(p =>
            {
                Progress = p.Total == 0 ? 0 : 100.0 * p.Current / p.Total;
                if (p.LastResult != null)
                {
                    UpdateQueueItem(p.LastResult);
                    Log(p.LastResult.Success
                        ? $"OK  {Path.GetFileName(p.LastResult.SourcePath)} → {p.LastResult.Message}"
                        : $"ERR {Path.GetFileName(p.LastResult.SourcePath)}: {p.LastResult.Message}");
                }
            });
            var results = await _jobs.RunShredBatchAsync(sources, options, progress, ct);
            var ok = results.Count(r => r.Success);
            StatusText = $"Shred complete: {ok}/{results.Count} succeeded.";
            if (results.LastOrDefault(r => r.Success)?.OutputPath is { } lastOut)
                BuildDiffFor(lastOut, results.Last(r => r.Success));
        });
    }

    [RelayCommand]
    private void OpenStudioImage()
    {
        var dlg = new OpenFileDialog
        {
            Filter = "Images|*.jpg;*.jpeg;*.jpe;*.jfif;*.png;*.tif;*.tiff;*.webp;*.bmp;*.gif;*.ico",
        };
        if (dlg.ShowDialog() == true)
        {
            StudioPath = dlg.FileName;
            LoadStudioFromPath(dlg.FileName);
        }
    }

    private void LoadStudioFromPath(string path)
    {
        ExifRows.Clear();
        foreach (var row in _images.LoadTags(path))
            ExifRows.Add(row);

        var fields = QuickFromTags(ExifRows);
        QuickMake = fields.GetValueOrDefault("Make") ?? "";
        QuickModel = fields.GetValueOrDefault("Model") ?? "";
        QuickSoftware = fields.GetValueOrDefault("Software") ?? "";
        QuickArtist = fields.GetValueOrDefault("Artist") ?? "";
        QuickDateTime = fields.GetValueOrDefault("DateTime") ?? fields.GetValueOrDefault("DateTimeOriginal") ?? "";
        QuickGpsLat = fields.GetValueOrDefault("GPSLatitude") ?? "";
        QuickGpsLon = fields.GetValueOrDefault("GPSLongitude") ?? "";

        StudioStatus = $"Loaded {Path.GetFileName(path)} · {ExifRows.Count} tags";
        DiffReport = string.Join(Environment.NewLine, _images.InspectSummary(path).Select(s => "• " + s));
    }

    [RelayCommand]
    private void ApplyQuickToTable()
    {
        void Set(string name, string value)
        {
            if (string.IsNullOrWhiteSpace(value)) return;
            var existing = ExifRows.FirstOrDefault(r =>
                string.Equals(Normalize(r.Name), Normalize(name), StringComparison.OrdinalIgnoreCase));
            if (existing != null) existing.Value = value;
            else ExifRows.Add(new ExifTagRow { Directory = "Exif", Name = name, Value = value, IsEditable = true });
        }
        Set("Make", QuickMake);
        Set("Model", QuickModel);
        Set("Software", QuickSoftware);
        Set("Artist", QuickArtist);
        Set("DateTime", QuickDateTime);
        Set("DateTimeOriginal", QuickDateTime);
        Set("GPSLatitude", QuickGpsLat);
        Set("GPSLongitude", QuickGpsLon);
        StudioStatus = "Quick fields applied to table (save to write).";
    }

    [RelayCommand]
    private async Task WriteExifAsync()
    {
        if (string.IsNullOrWhiteSpace(StudioPath) || !File.Exists(StudioPath)) return;
        var options = BuildOutputOptions(StudioOutputDirectory, StudioSuffix);
        options.Suffix = StudioSuffix;
        await RunJobAsync(async ct =>
        {
            var result = await _images.WriteExifAsync(StudioPath, ExifRows.ToList(), options, ct);
            StudioStatus = result.Message;
            StatusText = result.Message;
            Log(result.Success ? $"EXIF write OK: {result.Message}" : $"EXIF write failed: {result.Message}");
            if (result.Success && result.OutputPath != null)
            {
                DiffReport = "After write:\n" + string.Join("\n", _images.InspectSummary(result.OutputPath).Select(s => "• " + s));
            }
        });
    }

    [RelayCommand]
    private void OpenPdf()
    {
        var dlg = new OpenFileDialog { Filter = "PDF|*.pdf" };
        if (dlg.ShowDialog() == true)
        {
            PdfPath = dlg.FileName;
            LoadPdfFromPath(dlg.FileName);
        }
    }

    private void LoadPdfFromPath(string path)
    {
        PdfFileInfo.Clear();
        foreach (var (k, v) in _pdfs.LoadFileInfo(path))
            PdfFileInfo.Add(new KeyValueItem { Key = k, Value = v });

        PdfRows.Clear();
        foreach (var row in _pdfs.LoadMetadata(path))
            PdfRows.Add(row);

        PdfStatus = $"Loaded {Path.GetFileName(path)}";
        DiffReport = string.Join(Environment.NewLine,
            PdfRows.Where(r => !string.IsNullOrWhiteSpace(r.Value)).Select(r => $"• {r.Key}: {r.Value}"));
    }

    [RelayCommand]
    private async Task WritePdfAsync()
    {
        if (string.IsNullOrWhiteSpace(PdfPath) || !File.Exists(PdfPath)) return;
        var options = BuildOutputOptions(PdfOutputDirectory, PdfSuffix);
        options.StripXmp = PdfStripXmp;
        await RunJobAsync(async ct =>
        {
            var result = await _pdfs.WriteAsync(PdfPath, PdfRows.ToList(), options, stripAll: false, ct);
            PdfStatus = result.Message;
            StatusText = result.Message;
            Log(result.Success ? $"PDF write OK: {result.Message}" : $"PDF write failed: {result.Message}");
        });
    }

    [RelayCommand]
    private async Task ShredPdfAsync()
    {
        if (string.IsNullOrWhiteSpace(PdfPath) || !File.Exists(PdfPath)) return;
        var options = BuildOutputOptions(PdfOutputDirectory, string.IsNullOrEmpty(PdfSuffix) ? "_clean" : PdfSuffix);
        options.StripXmp = true;
        await RunJobAsync(async ct =>
        {
            var result = await _pdfs.WriteAsync(PdfPath, PdfRows.ToList(), options, stripAll: true, ct);
            PdfStatus = result.Message;
            StatusText = result.Message;
            Log(result.Success ? $"PDF shred OK: {result.Message}" : $"PDF shred failed: {result.Message}");
            if (result.Success && result.OutputPath != null)
            {
                VerifyReport = FormatFindings(_pdfs.Verify(result.OutputPath));
            }
        });
    }

    [RelayCommand]
    private void RandomMask()
    {
        var mask = _masks.PickRandom(SelectedCategory, SelectedRegion);
        if (MaskIdByLabel.ContainsValue(mask.Id))
        {
            SelectedMaskLabel = MaskIdByLabel.First(kv => kv.Value == mask.Id).Key;
        }
        PreviewScramble();
    }

    [RelayCommand]
    private void PreviewScramble()
    {
        var mask = CurrentMask();
        if (mask == null)
        {
            ScrambleStatus = "No mask selected.";
            return;
        }
        _lastPayload = ScrambleEngine.Build(mask, BuildScrambleOptions());
        ScramblePreview = _lastPayload.Summary + Environment.NewLine + Environment.NewLine
            + "EXIF:" + Environment.NewLine
            + string.Join(Environment.NewLine, _lastPayload.ExifFields.Select(kv => $"  {kv.Key} = {kv.Value}"))
            + Environment.NewLine + Environment.NewLine
            + "PDF:" + Environment.NewLine
            + string.Join(Environment.NewLine, _lastPayload.PdfFields.Select(kv => $"  {kv.Key} = {kv.Value}"));
        ScrambleStatus = "Preview ready — apply to Studio or batch-scramble the queue.";
    }

    [RelayCommand]
    private void ApplyScrambleToExifStudio()
    {
        PreviewScramble();
        if (_lastPayload == null) return;
        QuickMake = _lastPayload.ExifFields.GetValueOrDefault("Make") ?? "";
        QuickModel = _lastPayload.ExifFields.GetValueOrDefault("Model") ?? "";
        QuickSoftware = _lastPayload.ExifFields.GetValueOrDefault("Software") ?? "";
        QuickArtist = _lastPayload.ExifFields.GetValueOrDefault("Artist") ?? "";
        QuickDateTime = _lastPayload.ExifFields.GetValueOrDefault("DateTime") ?? "";
        QuickGpsLat = _lastPayload.ExifFields.GetValueOrDefault("GPSLatitude") ?? "";
        QuickGpsLon = _lastPayload.ExifFields.GetValueOrDefault("GPSLongitude") ?? "";
        ApplyQuickToTable();
        foreach (var (k, v) in _lastPayload.ExifFields)
        {
            var existing = ExifRows.FirstOrDefault(r =>
                string.Equals(Normalize(r.Name), Normalize(k), StringComparison.OrdinalIgnoreCase));
            if (existing != null) existing.Value = v;
            else ExifRows.Add(new ExifTagRow { Directory = "Exif", Name = k, Value = v, IsEditable = true });
        }
        StudioStatus = "Scramble applied to EXIF Studio — review and Write EXIF.";
        ScrambleStatus = StudioStatus;
    }

    [RelayCommand]
    private void ApplyScrambleToPdfStudio()
    {
        PreviewScramble();
        if (_lastPayload == null) return;
        foreach (var (k, v) in _lastPayload.PdfFields)
        {
            var row = PdfRows.FirstOrDefault(r => string.Equals(r.Key, k, StringComparison.OrdinalIgnoreCase));
            if (row != null) row.Value = v;
            else PdfRows.Add(new PdfMetaRow { Key = k, Value = v, IsEditable = true, IsStandard = true });
        }
        PdfStatus = "Scramble applied to PDF Studio — review and Write Metadata.";
        ScrambleStatus = PdfStatus;
    }

    [RelayCommand]
    private async Task ScrambleQueueAsync()
    {
        var mask = CurrentMask();
        if (mask == null || Queue.Count == 0) return;
        PreviewScramble();
        var options = BuildOutputOptions(OutputDirectory, ScrambleBatchSuffix);
        options.Suffix = ScrambleBatchSuffix;
        await RunJobAsync(async ct =>
        {
            var progress = new Progress<JobProgress>(p =>
            {
                Progress = p.Total == 0 ? 0 : 100.0 * p.Current / p.Total;
                if (p.LastResult != null)
                {
                    UpdateQueueItem(p.LastResult);
                    Log(p.LastResult.Success
                        ? $"MASK {Path.GetFileName(p.LastResult.SourcePath)} → {p.LastResult.Message}"
                        : $"ERR  {Path.GetFileName(p.LastResult.SourcePath)}: {p.LastResult.Message}");
                }
            });
            var results = await _jobs.RunScrambleBatchAsync(
                Queue.Select(q => q.Path).ToList(), mask, BuildScrambleOptions(), options, progress, ct);
            StatusText = $"Scramble complete: {results.Count(r => r.Success)}/{results.Count}";
            ScrambleStatus = StatusText;
        });
    }

    [RelayCommand]
    private void VerifySelected()
    {
        var path = SelectedQueueItem?.OutputPath
                   ?? SelectedQueueItem?.Path
                   ?? (!string.IsNullOrWhiteSpace(StudioPath) ? StudioPath : PdfPath);
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
        {
            VerifyReport = "Nothing to verify.";
            return;
        }

        var kind = SupportedFormats.Classify(path);
        var findings = kind == FileKind.Pdf ? _pdfs.Verify(path) : _images.Verify(path);
        VerifyReport = $"Verify: {Path.GetFileName(path)}\n" + FormatFindings(findings);
        Log($"Verified {Path.GetFileName(path)} · {findings.Count} finding(s)");
    }

    [RelayCommand]
    private void OpenOutputFolder()
    {
        var dir = OutputDirectory;
        if (!Directory.Exists(dir))
            Directory.CreateDirectory(dir);
        Process.Start(new ProcessStartInfo { FileName = dir, UseShellExecute = true });
    }

    [RelayCommand]
    private void CancelJob() => _cts?.Cancel();

    private void RefreshMasks()
    {
        MaskLabels.Clear();
        MaskIdByLabel.Clear();
        var list = _masks.Filter(SelectedCategory, SelectedRegion);
        foreach (var m in list)
        {
            MaskLabels.Add(m.Label);
            MaskIdByLabel[m.Label] = m.Id;
        }
        MaskCountText = $"{list.Count} mask(s)";
        if (list.Count > 0 && (string.IsNullOrEmpty(SelectedMaskLabel) || !MaskIdByLabel.ContainsKey(SelectedMaskLabel)))
            SelectedMaskLabel = list[0].Label;
    }

    private DeviceMask? CurrentMask()
    {
        if (string.IsNullOrEmpty(SelectedMaskLabel) || !MaskIdByLabel.TryGetValue(SelectedMaskLabel, out var id))
            return null;
        return _masks.GetById(id);
    }

    private ScrambleOptions BuildScrambleOptions() => new()
    {
        RandomizeGps = ScrambleGps,
        RandomizeDateTime = ScrambleDates,
        RandomizeExposure = ScrambleExposure,
        SetArtist = !string.IsNullOrWhiteSpace(ScrambleArtist),
        ArtistName = ScrambleArtist,
        UserComment = ScrambleComment,
    };

    private OutputOptions BuildOutputOptions(string dir, string suffix) => new()
    {
        OutputDirectory = dir,
        Suffix = suffix,
        Overwrite = Overwrite,
        OverwriteSourceInPlace = OverwriteInPlace,
        KeepIcc = KeepIcc,
        StripXmp = PdfStripXmp,
        VerifyAfterWrite = VerifyAfter,
    };

    private async Task RunJobAsync(Func<CancellationToken, Task> work)
    {
        if (IsBusy) return;
        IsBusy = true;
        Progress = 0;
        _cts = new CancellationTokenSource();
        try
        {
            await work(_cts.Token);
        }
        catch (OperationCanceledException)
        {
            StatusText = "Cancelled.";
            Log("Job cancelled.");
        }
        catch (Exception ex)
        {
            StatusText = "Error: " + ex.Message;
            Log("ERROR " + ex.Message);
            MessageBox.Show(ex.Message, "EXIFexit", MessageBoxButton.OK, MessageBoxImage.Error);
        }
        finally
        {
            IsBusy = false;
            _cts.Dispose();
            _cts = null;
        }
    }

    private void UpdateQueueItem(OperationResult result)
    {
        var item = Queue.FirstOrDefault(q =>
            string.Equals(q.Path, result.SourcePath, StringComparison.OrdinalIgnoreCase));
        if (item == null) return;
        item.Status = result.Success ? JobItemStatus.Succeeded : JobItemStatus.Failed;
        item.StatusText = result.Message;
        item.OutputPath = result.OutputPath;
    }

    private void BuildDiffFor(string outputPath, OperationResult result)
    {
        DiffReport =
            $"Source: {Path.GetFileName(result.SourcePath)}\n" +
            $"Output: {Path.GetFileName(outputPath)}\n\n" +
            "Removed groups:\n" +
            string.Join("\n", result.TagsRemoved.Select(t => "− " + t)) +
            "\n\nResidual:\n" +
            FormatFindings(result.ResidualFindings);
    }

    private static string FormatFindings(IReadOnlyList<MetadataFinding> findings)
    {
        if (findings.Count == 0) return "✓ No residual sensitive metadata found.";
        return string.Join(Environment.NewLine,
            findings.Select(f => $"{(f.IsSensitive ? "!" : "·")} [{f.Category}] {f.Detail}"));
    }

    private void Log(string line) =>
        System.Windows.Application.Current?.Dispatcher.Invoke(() =>
        {
            LogLines.Insert(0, $"[{DateTime.Now:HH:mm:ss}] {line}");
            while (LogLines.Count > 400) LogLines.RemoveAt(LogLines.Count - 1);
        });

    private static Dictionary<string, string> QuickFromTags(IEnumerable<ExifTagRow> rows)
    {
        var d = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var r in rows)
        {
            var n = Normalize(r.Name);
            if (!d.ContainsKey(n))
                d[n] = r.Value;
            // also store common aliases
            if (r.Name.Contains("Make", StringComparison.OrdinalIgnoreCase)) d["Make"] = r.Value;
            if (r.Name.Equals("Model", StringComparison.OrdinalIgnoreCase)) d["Model"] = r.Value;
        }
        return d;
    }

    private static string Normalize(string name) =>
        name.Replace("Date/Time Original", "DateTimeOriginal", StringComparison.OrdinalIgnoreCase)
            .Replace("Date/Time", "DateTime", StringComparison.OrdinalIgnoreCase)
            .Replace(" ", "")
            .Replace("/", "");
}

public partial class QueueItemVm : ObservableObject
{
    public required string Path { get; init; }
    public required FileKind Kind { get; init; }
    public required string DisplayName { get; init; }
    public string MetaSummary { get; set; } = "";
    public string? OutputPath { get; set; }

    [ObservableProperty] private JobItemStatus _status;
    [ObservableProperty] private string _statusText = "Pending";

    public string KindLabel => Kind == FileKind.Pdf ? "PDF" : "IMG";
}

public sealed class KeyValueItem
{
    public string Key { get; set; } = "";
    public string Value { get; set; } = "";
}
