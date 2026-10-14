using EXIFexit.Domain.Models;

namespace EXIFexit.Domain.Scramble;

/// <summary>Pure scramble engine — no I/O, no tool fingerprints.</summary>
public static class ScrambleEngine
{
    public static ScramblePayload Build(
        DeviceMask mask,
        ScrambleOptions? options = null,
        Random? rng = null)
    {
        options ??= new ScrambleOptions();
        rng ??= Random.Shared;

        DateTime dt;
        if (options.RandomizeDateTime)
        {
            var min = Math.Min(options.DaysBackMin, options.DaysBackMax);
            var max = Math.Max(options.DaysBackMin, options.DaysBackMax);
            var days = rng.Next(min, max + 1);
            var seconds = rng.Next(0, 86400);
            dt = DateTime.Now.AddDays(-days).AddSeconds(-seconds);
        }
        else
        {
            dt = DateTime.Now;
        }

        var lat = mask.GpsLat;
        var lon = mask.GpsLon;
        if (options.RandomizeGps && (Math.Abs(lat) > 0.000001 || Math.Abs(lon) > 0.000001))
            (lat, lon) = JitterGps(lat, lon, options.GpsJitterKm, rng);

        var latRef = lat >= 0 ? "N" : "S";
        var lonRef = lon >= 0 ? "E" : "W";
        var absLat = Math.Abs(lat);
        var absLon = Math.Abs(lon);
        var stamp = dt.ToString("yyyy:MM:dd HH:mm:ss");

        var software = mask.Software;
        if (options.RandomizeDateTime && rng.NextDouble() < 0.35)
            software = $"{software}.{rng.Next(0, 10)}";

        var exif = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["Make"] = mask.Make,
            ["Model"] = mask.Model,
            ["Software"] = software,
            ["DateTime"] = stamp,
            ["DateTimeOriginal"] = stamp,
            ["DateTimeDigitized"] = stamp,
            ["GPSLatitude"] = absLat.ToString("F6"),
            ["GPSLatitudeRef"] = latRef,
            ["GPSLongitude"] = absLon.ToString("F6"),
            ["GPSLongitudeRef"] = lonRef,
            ["GPSAltitude"] = rng.Next(5, 421).ToString(),
            ["GPSAltitudeRef"] = "0",
        };

        if (!string.IsNullOrWhiteSpace(mask.LensModel))
            exif["LensModel"] = mask.LensModel;
        if (!string.IsNullOrWhiteSpace(mask.LensMake))
            exif["LensMake"] = mask.LensMake;

        if (options.RandomizeExposure && IsCaptureDevice(mask.Category))
        {
            foreach (var (k, v) in FakeExposure(rng))
                exif[k] = v;
        }

        if (options.SetArtist && !string.IsNullOrWhiteSpace(options.ArtistName))
        {
            exif["Artist"] = options.ArtistName.Trim();
            exif["Copyright"] = $"© {dt.Year} {options.ArtistName.Trim()}";
        }
        else if (!string.IsNullOrWhiteSpace(mask.Artist))
        {
            exif["Artist"] = mask.Artist;
        }

        // Anti-fingerprint: never mention EXIFexit or "Device mask"
        if (!string.IsNullOrWhiteSpace(options.UserComment))
            exif["UserComment"] = options.UserComment.Trim();
        else
            exif["UserComment"] = $"Captured in {mask.City}, {mask.Country}";

        exif["ImageDescription"] = $"{mask.City} · {mask.Model}";

        var author = FirstNonEmpty(options.PdfAuthor, options.ArtistName, mask.Make);
        var title = FirstNonEmpty(options.PdfTitle, $"Document · {mask.City}");
        var subject = FirstNonEmpty(options.PdfSubject, $"Authored on {mask.Label}");
        var keywords = FirstNonEmpty(options.PdfKeywords, $"{mask.Region}, {mask.Category}, {mask.Model}");
        var pdfDt = FormatPdfDate(dt, mask.TimezoneOffset);

        var pdf = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["Title"] = title,
            ["Author"] = author,
            ["Subject"] = subject,
            ["Keywords"] = keywords,
            ["Creator"] = FirstNonEmpty(mask.Creator, mask.Software),
            ["Producer"] = FirstNonEmpty(mask.Producer, mask.Software),
            ["CreationDate"] = pdfDt,
            ["ModDate"] = pdfDt,
            ["Trapped"] = "False",
        };

        var summary =
            $"{mask.Label}  ·  {mask.City}, {mask.Country}  ·  " +
            $"GPS {latRef}{absLat:F4} {lonRef}{absLon:F4}  ·  {stamp}";

        return new ScramblePayload
        {
            Mask = mask,
            ExifFields = exif,
            PdfFields = pdf,
            Summary = summary,
        };
    }

    private static bool IsCaptureDevice(string category) =>
        category is "phone" or "camera" or "drone" or "tablet";

    private static (double Lat, double Lon) JitterGps(double lat, double lon, double km, Random rng)
    {
        if (km <= 0) return (lat, lon);
        var dlat = (rng.NextDouble() * 2 - 1) * km / 111.0;
        var cosLat = Math.Max(0.2, Math.Abs(Math.Cos(lat * Math.PI / 180.0)));
        var dlon = (rng.NextDouble() * 2 - 1) * km / (111.0 * cosLat);
        var nlat = Math.Clamp(lat + dlat, -90.0, 90.0);
        var nlon = ((lon + dlon + 180.0) % 360.0) - 180.0;
        return (nlat, nlon);
    }

    private static Dictionary<string, string> FakeExposure(Random rng)
    {
        string[] shutters = ["1/30", "1/60", "1/125", "1/250", "1/500", "1/1000", "1/2000"];
        string[] apertures = ["1.4", "1.8", "2.0", "2.8", "4.0", "5.6", "8.0"];
        string[] isos = ["100", "200", "400", "800", "1600", "3200"];
        string[] focals = ["24", "28", "35", "50", "70", "85", "105", "135", "200"];
        return new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["ExposureTime"] = shutters[rng.Next(shutters.Length)],
            ["FNumber"] = apertures[rng.Next(apertures.Length)],
            ["ISOSpeedRatings"] = isos[rng.Next(isos.Length)],
            ["FocalLength"] = focals[rng.Next(focals.Length)],
        };
    }

    private static string FormatPdfDate(DateTime dt, string tzOffset)
    {
        var raw = dt.ToString("yyyyMMddHHmmss");
        var off = (tzOffset ?? "").Trim();
        if (off.Length >= 3 && (off[0] is '+' or '-') && off.Contains(':'))
        {
            var sign = off[0];
            var parts = off[1..].Split(':');
            if (parts.Length >= 2)
                return $"D:{raw}{sign}{parts[0]}'{parts[1]}'";
        }
        return $"D:{raw}";
    }

    private static string FirstNonEmpty(params string?[] values)
    {
        foreach (var v in values)
        {
            if (!string.IsNullOrWhiteSpace(v))
                return v.Trim();
        }
        return "";
    }
}
