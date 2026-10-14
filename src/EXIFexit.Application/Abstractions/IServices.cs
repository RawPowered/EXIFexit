using EXIFexit.Domain.Models;

namespace EXIFexit.Application.Abstractions;

public interface IImageMetadataService
{
    IReadOnlyList<string> InspectSummary(string path);
    IReadOnlyList<ExifTagRow> LoadTags(string path);
    IReadOnlyList<MetadataFinding> Verify(string path);
    Task<OperationResult> ShredAsync(string sourcePath, OutputOptions options, CancellationToken ct = default);
    Task<OperationResult> WriteExifAsync(
        string sourcePath,
        IReadOnlyList<ExifTagRow> tags,
        OutputOptions options,
        CancellationToken ct = default);
    Task<OperationResult> WriteQuickFieldsAsync(
        string sourcePath,
        IReadOnlyDictionary<string, string> fields,
        OutputOptions options,
        CancellationToken ct = default);
}

public interface IPdfMetadataService
{
    IReadOnlyList<(string Key, string Value)> LoadFileInfo(string path);
    IReadOnlyList<PdfMetaRow> LoadMetadata(string path);
    IReadOnlyList<MetadataFinding> Verify(string path);
    Task<OperationResult> WriteAsync(
        string sourcePath,
        IReadOnlyList<PdfMetaRow> rows,
        OutputOptions options,
        bool stripAll,
        CancellationToken ct = default);
}

public interface IMaskCatalog
{
    IReadOnlyList<DeviceMask> All { get; }
    IReadOnlyList<string> Categories { get; }
    IReadOnlyDictionary<string, string> RegionLabels { get; }
    DeviceMask? GetById(string id);
    IReadOnlyList<DeviceMask> Filter(string? category, string? region);
    DeviceMask PickRandom(string? category, string? region, Random? rng = null);
}

public interface IPathPolicy
{
    string ResolveOutputPath(
        string sourcePath,
        string outputDirectory,
        string suffix,
        bool overwrite,
        string? forceExtension = null);
}

public interface ILocaleService
{
    IReadOnlyDictionary<string, string> Languages { get; }
    string CurrentCode { get; }
    void SetLanguage(string code);
    string T(string key, string? fallback = null);
    event EventHandler? LanguageChanged;
}

public interface IJobRunner
{
    Task<IReadOnlyList<OperationResult>> RunShredBatchAsync(
        IReadOnlyList<string> sources,
        OutputOptions options,
        IProgress<JobProgress>? progress = null,
        CancellationToken ct = default);

    Task<IReadOnlyList<OperationResult>> RunScrambleBatchAsync(
        IReadOnlyList<string> sources,
        DeviceMask mask,
        ScrambleOptions scrambleOptions,
        OutputOptions options,
        IProgress<JobProgress>? progress = null,
        CancellationToken ct = default);
}

public sealed class JobProgress
{
    public int Current { get; init; }
    public int Total { get; init; }
    public OperationResult? LastResult { get; init; }
}
