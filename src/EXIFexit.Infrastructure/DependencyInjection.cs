using EXIFexit.Application.Abstractions;
using EXIFexit.Application.Services;
using EXIFexit.Infrastructure.Imaging;
using EXIFexit.Infrastructure.Localization;
using EXIFexit.Infrastructure.Masks;
using EXIFexit.Infrastructure.Paths;
using EXIFexit.Infrastructure.Pdf;
using Microsoft.Extensions.DependencyInjection;

namespace EXIFexit.Infrastructure;

public static class DependencyInjection
{
    public static IServiceCollection AddExifExit(this IServiceCollection services, string contentRoot)
    {
        var masksPath = Path.Combine(contentRoot, "data", "masks", "core.json");
        var localesDir = Path.Combine(contentRoot, "data", "locales");

        // Also try next to the executable (published layout)
        if (!File.Exists(masksPath))
        {
            var baseDir = AppContext.BaseDirectory;
            var altMasks = Path.Combine(baseDir, "data", "masks", "core.json");
            if (File.Exists(altMasks))
            {
                masksPath = altMasks;
                localesDir = Path.Combine(baseDir, "data", "locales");
            }
        }

        services.AddSingleton<IPathPolicy, PathPolicy>();
        services.AddSingleton<IMaskCatalog>(_ => new JsonMaskCatalog(masksPath));
        services.AddSingleton<ILocaleService>(_ => new JsonLocaleService(localesDir));
        services.AddSingleton<IImageMetadataService, ImageMetadataService>();
        services.AddSingleton<IPdfMetadataService, PdfMetadataService>();
        services.AddSingleton<IJobRunner, JobRunner>();
        return services;
    }
}
