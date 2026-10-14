using EXIFexit.Application.Abstractions;

namespace EXIFexit.Infrastructure.Paths;

public sealed class PathPolicy : IPathPolicy
{
    public string ResolveOutputPath(
        string sourcePath,
        string outputDirectory,
        string suffix,
        bool overwrite,
        string? forceExtension = null)
    {
        Directory.CreateDirectory(outputDirectory);
        var stem = Path.GetFileNameWithoutExtension(sourcePath);
        var ext = forceExtension ?? Path.GetExtension(sourcePath);
        if (string.Equals(ext, ".jpe", StringComparison.OrdinalIgnoreCase) ||
            string.Equals(ext, ".jfif", StringComparison.OrdinalIgnoreCase))
            ext = ".jpg";

        var name = string.IsNullOrEmpty(suffix) ? $"{stem}{ext}" : $"{stem}{suffix}{ext}";
        var path = Path.Combine(outputDirectory, name);
        if (overwrite || !File.Exists(path))
            return path;

        var n = 1;
        while (true)
        {
            name = string.IsNullOrEmpty(suffix)
                ? $"{stem} ({n}){ext}"
                : $"{stem}{suffix} ({n}){ext}";
            path = Path.Combine(outputDirectory, name);
            if (!File.Exists(path))
                return path;
            n++;
        }
    }

    public static async Task AtomicWriteAsync(string destination, Func<string, Task> writeTempAsync)
    {
        var dir = Path.GetDirectoryName(destination) ?? ".";
        Directory.CreateDirectory(dir);
        var tmp = destination + ".exifexit.tmp";
        try
        {
            if (File.Exists(tmp))
                File.Delete(tmp);
            await writeTempAsync(tmp).ConfigureAwait(false);
            if (File.Exists(destination))
            {
                File.Replace(tmp, destination, destination + ".bak", ignoreMetadataErrors: true);
                try { File.Delete(destination + ".bak"); } catch { /* best effort */ }
            }
            else
            {
                File.Move(tmp, destination);
            }
        }
        finally
        {
            try { if (File.Exists(tmp)) File.Delete(tmp); } catch { /* ignore */ }
        }
    }
}
