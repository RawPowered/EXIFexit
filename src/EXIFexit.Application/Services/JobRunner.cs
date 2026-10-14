using EXIFexit.Application.Abstractions;
using EXIFexit.Domain.Models;
using EXIFexit.Domain.Scramble;

namespace EXIFexit.Application.Services;

public sealed class JobRunner : IJobRunner
{
    private readonly IImageMetadataService _images;
    private readonly IPdfMetadataService _pdfs;

    public JobRunner(IImageMetadataService images, IPdfMetadataService pdfs)
    {
        _images = images;
        _pdfs = pdfs;
    }

    public async Task<IReadOnlyList<OperationResult>> RunShredBatchAsync(
        IReadOnlyList<string> sources,
        OutputOptions options,
        IProgress<JobProgress>? progress = null,
        CancellationToken ct = default)
    {
        var results = new List<OperationResult>(sources.Count);
        for (var i = 0; i < sources.Count; i++)
        {
            ct.ThrowIfCancellationRequested();
            var path = sources[i];
            OperationResult result;
            var kind = SupportedFormats.Classify(path);
            try
            {
                result = kind switch
                {
                    FileKind.Image => await _images.ShredAsync(path, options, ct).ConfigureAwait(false),
                    FileKind.Pdf => await _pdfs.WriteAsync(path, Array.Empty<PdfMetaRow>(), options, stripAll: true, ct)
                        .ConfigureAwait(false),
                    _ => new OperationResult
                    {
                        SourcePath = path,
                        Success = false,
                        Message = "Unsupported file type",
                    },
                };
            }
            catch (Exception ex)
            {
                result = new OperationResult
                {
                    SourcePath = path,
                    Success = false,
                    Message = ex.Message,
                };
            }

            results.Add(result);
            progress?.Report(new JobProgress { Current = i + 1, Total = sources.Count, LastResult = result });
        }

        return results;
    }

    public async Task<IReadOnlyList<OperationResult>> RunScrambleBatchAsync(
        IReadOnlyList<string> sources,
        DeviceMask mask,
        ScrambleOptions scrambleOptions,
        OutputOptions options,
        IProgress<JobProgress>? progress = null,
        CancellationToken ct = default)
    {
        var results = new List<OperationResult>(sources.Count);
        for (var i = 0; i < sources.Count; i++)
        {
            ct.ThrowIfCancellationRequested();
            var path = sources[i];
            // Per-file entropy so batch outputs don't share identical timestamps/GPS
            var rng = new Random(HashCode.Combine(path, mask.Id, i, Environment.TickCount));
            var payload = ScrambleEngine.Build(mask, scrambleOptions, rng);
            OperationResult result;
            var kind = SupportedFormats.Classify(path);
            try
            {
                result = kind switch
                {
                    FileKind.Image => await _images.WriteQuickFieldsAsync(path, payload.ExifFields, options, ct)
                        .ConfigureAwait(false),
                    FileKind.Pdf => await WritePdfScrambleAsync(path, payload, options, ct).ConfigureAwait(false),
                    _ => new OperationResult
                    {
                        SourcePath = path,
                        Success = false,
                        Message = "Unsupported file type",
                    },
                };
            }
            catch (Exception ex)
            {
                result = new OperationResult
                {
                    SourcePath = path,
                    Success = false,
                    Message = ex.Message,
                };
            }

            results.Add(result);
            progress?.Report(new JobProgress { Current = i + 1, Total = sources.Count, LastResult = result });
        }

        return results;
    }

    private async Task<OperationResult> WritePdfScrambleAsync(
        string path,
        ScramblePayload payload,
        OutputOptions options,
        CancellationToken ct)
    {
        var rows = payload.PdfFields
            .Select(kv => new PdfMetaRow { Key = kv.Key, Value = kv.Value, IsEditable = true, IsStandard = true })
            .ToList();
        return await _pdfs.WriteAsync(path, rows, options, stripAll: false, ct).ConfigureAwait(false);
    }
}
