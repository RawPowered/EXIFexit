using EXIFexit.Infrastructure.Imaging;
using EXIFexit.Infrastructure.Paths;
using FluentAssertions;
using SixLabors.ImageSharp;
using SixLabors.ImageSharp.PixelFormats;

namespace EXIFexit.Infrastructure.Tests;

public class JpegAndExifTests
{
    [Fact]
    public async Task Jpeg_StripMetadata_RemovesExifApp1()
    {
        var dir = Path.Combine(Path.GetTempPath(), "exifexit-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        try
        {
            var src = Path.Combine(dir, "with-meta.jpg");
            await CreateJpegWithExifAsync(src);

            var bytes = await File.ReadAllBytesAsync(src);
            var clean = JpegSegmentEditor.StripMetadata(bytes);
            clean.Should().NotBeEmpty();
            // EXIF header should be gone
            FindAscii(clean, "Exif").Should().BeFalse();

            var outPath = Path.Combine(dir, "clean.jpg");
            await File.WriteAllBytesAsync(outPath, clean);
            using var img = await Image.LoadAsync(outPath);
            img.Width.Should().BeGreaterThan(0);
        }
        finally
        {
            try { Directory.Delete(dir, true); } catch { /* ignore */ }
        }
    }

    [Fact]
    public async Task Jpeg_UpsertExif_WritesMakeModel()
    {
        var dir = Path.Combine(Path.GetTempPath(), "exifexit-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        try
        {
            var src = Path.Combine(dir, "base.jpg");
            using (var image = new Image<Rgba32>(32, 24))
            {
                await image.SaveAsJpegAsync(src);
            }

            var fields = new Dictionary<string, string>
            {
                ["Make"] = "Canon",
                ["Model"] = "EOS R5",
                ["DateTime"] = "2026:01:15 12:00:00",
            };
            var app1 = ExifBuilder.BuildApp1Payload(fields);
            app1[0].Should().Be((byte)'E');
            var jpeg = await File.ReadAllBytesAsync(src);
            var updated = JpegSegmentEditor.UpsertExifApp1(jpeg, app1);
            FindAscii(updated, "Canon").Should().BeTrue();
            FindAscii(updated, "EOS R5").Should().BeTrue();

            var outPath = Path.Combine(dir, "edited.jpg");
            await File.WriteAllBytesAsync(outPath, updated);

            var service = new ImageMetadataService(new PathPolicy());
            var summary = service.InspectSummary(outPath);
            summary.Should().NotBeEmpty();
        }
        finally
        {
            try { Directory.Delete(dir, true); } catch { /* ignore */ }
        }
    }

    private static async Task CreateJpegWithExifAsync(string path)
    {
        using var image = new Image<Rgba32>(64, 48);
        var fields = new Dictionary<string, string>
        {
            ["Make"] = "Apple",
            ["Model"] = "iPhone",
            ["GPSLatitude"] = "30.2672",
            ["GPSLatitudeRef"] = "N",
            ["GPSLongitude"] = "97.7431",
            ["GPSLongitudeRef"] = "W",
        };
        await image.SaveAsJpegAsync(path);
        var jpeg = await File.ReadAllBytesAsync(path);
        var app1 = ExifBuilder.BuildApp1Payload(fields);
        var withExif = JpegSegmentEditor.UpsertExifApp1(jpeg, app1);
        await File.WriteAllBytesAsync(path, withExif);
    }

    private static bool FindAscii(byte[] data, string text)
    {
        var needle = System.Text.Encoding.ASCII.GetBytes(text);
        for (var i = 0; i <= data.Length - needle.Length; i++)
        {
            var ok = true;
            for (var j = 0; j < needle.Length; j++)
            {
                if (data[i + j] != needle[j]) { ok = false; break; }
            }
            if (ok) return true;
        }
        return false;
    }
}
