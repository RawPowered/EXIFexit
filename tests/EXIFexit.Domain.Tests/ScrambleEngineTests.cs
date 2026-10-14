using EXIFexit.Domain.Models;
using EXIFexit.Domain.Scramble;
using FluentAssertions;

namespace EXIFexit.Domain.Tests;

public class ScrambleEngineTests
{
    [Fact]
    public void Build_DoesNotFingerprintTool()
    {
        var mask = new DeviceMask
        {
            Id = "test",
            Label = "Test Phone",
            Category = "phone",
            Region = "US",
            Country = "United States",
            City = "Austin",
            Make = "Google",
            Model = "Pixel 8",
            Software = "HDR+ 1.0",
            GpsLat = 30.2672,
            GpsLon = -97.7431,
            Creator = "Photos",
            Producer = "Android",
            TimezoneOffset = "-06:00",
        };

        var payload = ScrambleEngine.Build(mask, new ScrambleOptions(), new Random(42));

        payload.ExifFields.Values.Should().NotContain(v => v.Contains("EXIFexit", StringComparison.OrdinalIgnoreCase));
        payload.ExifFields.Values.Should().NotContain(v => v.Contains("Device mask", StringComparison.OrdinalIgnoreCase));
        payload.PdfFields.Values.Should().NotContain(v => v.Contains("EXIFexit", StringComparison.OrdinalIgnoreCase));
        payload.ExifFields.Should().ContainKey("Make").WhoseValue.Should().Be("Google");
        payload.ExifFields.Should().ContainKey("Model").WhoseValue.Should().Be("Pixel 8");
        payload.Summary.Should().Contain("Austin");
    }

    [Fact]
    public void Build_PerSeedEntropy_Differs()
    {
        var mask = new DeviceMask
        {
            Id = "t", Label = "L", Category = "camera", Region = "JP",
            Country = "Japan", City = "Tokyo", Make = "Sony", Model = "A7",
            Software = "1.0", GpsLat = 35.68, GpsLon = 139.69,
        };
        var a = ScrambleEngine.Build(mask, rng: new Random(1));
        var b = ScrambleEngine.Build(mask, rng: new Random(2));
        a.ExifFields["DateTime"].Should().NotBe(b.ExifFields["DateTime"]);
    }
}
