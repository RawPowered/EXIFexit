using System.Buffers.Binary;
using System.Globalization;
using System.Text;

namespace EXIFexit.Infrastructure.Imaging;

/// <summary>
/// Minimal TIFF/EXIF builder for common tags used by Studio + Scramble.
/// Produces APP1 payload: "Exif\0\0" + little-endian TIFF.
/// </summary>
public static class ExifBuilder
{
    private const ushort TagImageDescription = 0x010E;
    private const ushort TagMake = 0x010F;
    private const ushort TagModel = 0x0110;
    private const ushort TagOrientation = 0x0112;
    private const ushort TagXResolution = 0x011A;
    private const ushort TagYResolution = 0x011B;
    private const ushort TagResolutionUnit = 0x0128;
    private const ushort TagSoftware = 0x0131;
    private const ushort TagDateTime = 0x0132;
    private const ushort TagArtist = 0x013B;
    private const ushort TagCopyright = 0x8298;
    private const ushort TagExifIfd = 0x8769;
    private const ushort TagGpsIfd = 0x8825;

    private const ushort TagExposureTime = 0x829A;
    private const ushort TagFNumber = 0x829D;
    private const ushort TagIso = 0x8827;
    private const ushort TagExifVersion = 0x9000;
    private const ushort TagDateTimeOriginal = 0x9003;
    private const ushort TagDateTimeDigitized = 0x9004;
    private const ushort TagFocalLength = 0x920A;
    private const ushort TagUserComment = 0x9286;
    private const ushort TagLensMake = 0xA433;
    private const ushort TagLensModel = 0xA434;

    private const ushort TagGpsVersion = 0x0000;
    private const ushort TagGpsLatRef = 0x0001;
    private const ushort TagGpsLat = 0x0002;
    private const ushort TagGpsLonRef = 0x0003;
    private const ushort TagGpsLon = 0x0004;
    private const ushort TagGpsAltRef = 0x0005;
    private const ushort TagGpsAlt = 0x0006;

    public static byte[] BuildApp1Payload(IReadOnlyDictionary<string, string> fields)
    {
        var map = new Dictionary<string, string>(fields, StringComparer.OrdinalIgnoreCase);
        var tiff = BuildTiff(map);
        var app1 = new byte[6 + tiff.Length];
        app1[0] = (byte)'E';
        app1[1] = (byte)'x';
        app1[2] = (byte)'i';
        app1[3] = (byte)'f';
        app1[4] = 0;
        app1[5] = 0;
        Buffer.BlockCopy(tiff, 0, app1, 6, tiff.Length);
        return app1;
    }

    private static byte[] BuildTiff(Dictionary<string, string> map)
    {
        var ifd0 = new List<IfdEntry>();
        var exif = new List<IfdEntry>();
        var gps = new List<IfdEntry>();

        void Ascii(List<IfdEntry> list, ushort tag, string? value)
        {
            if (!string.IsNullOrEmpty(value))
                list.Add(IfdEntry.Ascii(tag, value));
        }

        Ascii(ifd0, TagMake, Get(map, "Make"));
        Ascii(ifd0, TagModel, Get(map, "Model"));
        Ascii(ifd0, TagSoftware, Get(map, "Software"));
        Ascii(ifd0, TagDateTime, Get(map, "DateTime"));
        Ascii(ifd0, TagArtist, Get(map, "Artist"));
        Ascii(ifd0, TagCopyright, Get(map, "Copyright"));
        Ascii(ifd0, TagImageDescription, Get(map, "ImageDescription"));

        if (TryParseUShort(Get(map, "Orientation"), out var orient))
            ifd0.Add(IfdEntry.Short(TagOrientation, orient));

        ifd0.Add(IfdEntry.Rational(TagXResolution, 72, 1));
        ifd0.Add(IfdEntry.Rational(TagYResolution, 72, 1));
        ifd0.Add(IfdEntry.Short(TagResolutionUnit, 2));

        Ascii(exif, TagDateTimeOriginal, Get(map, "DateTimeOriginal") ?? Get(map, "DateTime"));
        Ascii(exif, TagDateTimeDigitized, Get(map, "DateTimeDigitized") ?? Get(map, "DateTime"));
        Ascii(exif, TagLensMake, Get(map, "LensMake"));
        Ascii(exif, TagLensModel, Get(map, "LensModel"));
        exif.Add(IfdEntry.Undefined(TagExifVersion, "0232"u8.ToArray()));

        if (TryParseRational(Get(map, "ExposureTime"), out var etNum, out var etDen))
            exif.Add(IfdEntry.Rational(TagExposureTime, etNum, etDen));
        if (TryParseRational(Get(map, "FNumber"), out var fNum, out var fDen))
            exif.Add(IfdEntry.Rational(TagFNumber, fNum, fDen));
        if (TryParseUShort(Get(map, "ISOSpeedRatings"), out var iso) || TryParseUShort(Get(map, "ISO"), out iso))
            exif.Add(IfdEntry.Short(TagIso, iso));
        if (TryParseRational(Get(map, "FocalLength"), out var flNum, out var flDen))
            exif.Add(IfdEntry.Rational(TagFocalLength, flNum, flDen));

        var comment = Get(map, "UserComment");
        if (!string.IsNullOrEmpty(comment))
        {
            var ascii = Encoding.ASCII.GetBytes(comment);
            var blob = new byte[8 + ascii.Length];
            blob[0] = (byte)'A';
            blob[1] = (byte)'S';
            blob[2] = (byte)'C';
            blob[3] = (byte)'I';
            blob[4] = (byte)'I';
            Buffer.BlockCopy(ascii, 0, blob, 8, ascii.Length);
            exif.Add(IfdEntry.Undefined(TagUserComment, blob));
        }

        var hasGps = map.Keys.Any(k => k.StartsWith("GPS", StringComparison.OrdinalIgnoreCase));
        if (hasGps)
        {
            gps.Add(IfdEntry.ByteArray(TagGpsVersion, [2, 3, 0, 0]));
            var latRef = Get(map, "GPSLatitudeRef") ?? "N";
            var lonRef = Get(map, "GPSLongitudeRef") ?? "E";
            Ascii(gps, TagGpsLatRef, latRef[..1]);
            Ascii(gps, TagGpsLonRef, lonRef[..1]);
            if (TryParseGps(Get(map, "GPSLatitude"), out var latR))
                gps.Add(IfdEntry.GpsRational(TagGpsLat, latR));
            if (TryParseGps(Get(map, "GPSLongitude"), out var lonR))
                gps.Add(IfdEntry.GpsRational(TagGpsLon, lonR));
            if (TryParseUShort(Get(map, "GPSAltitudeRef"), out var altRef))
                gps.Add(IfdEntry.Byte(TagGpsAltRef, (byte)altRef));
            else
                gps.Add(IfdEntry.Byte(TagGpsAltRef, 0));
            if (TryParseRational(Get(map, "GPSAltitude"), out var aNum, out var aDen))
                gps.Add(IfdEntry.Rational(TagGpsAlt, aNum, aDen));
        }

        // Pointers patched after layout
        if (exif.Count > 0)
            ifd0.Add(IfdEntry.Long(TagExifIfd, 0));
        if (gps.Count > 0)
            ifd0.Add(IfdEntry.Long(TagGpsIfd, 0));

        ifd0 = ifd0.OrderBy(e => e.Tag).ToList();
        exif = exif.OrderBy(e => e.Tag).ToList();
        gps = gps.OrderBy(e => e.Tag).ToList();

        const uint ifd0Offset = 8;
        var ifd0Block = IfdBlockSize(ifd0);
        var data0 = ExtraDataSize(ifd0);
        var exifOffset = ifd0Offset + ifd0Block + data0;
        var exifBlock = exif.Count > 0 ? IfdBlockSize(exif) : 0u;
        var dataE = ExtraDataSize(exif);
        var gpsOffset = exifOffset + exifBlock + dataE;

        for (var i = 0; i < ifd0.Count; i++)
        {
            if (ifd0[i].Tag == TagExifIfd)
                ifd0[i] = IfdEntry.Long(TagExifIfd, exifOffset);
            else if (ifd0[i].Tag == TagGpsIfd)
                ifd0[i] = IfdEntry.Long(TagGpsIfd, gpsOffset);
        }
        ifd0 = ifd0.OrderBy(e => e.Tag).ToList();

        using var ms = new MemoryStream();
        ms.WriteByte((byte)'I');
        ms.WriteByte((byte)'I');
        WriteU16(ms, 42);
        WriteU32(ms, ifd0Offset);

        WriteIfdWithData(ms, ifd0, ifd0Offset);
        if (exif.Count > 0)
            WriteIfdWithData(ms, exif, exifOffset);
        if (gps.Count > 0)
            WriteIfdWithData(ms, gps, gpsOffset);

        return ms.ToArray();
    }

    private static uint IfdBlockSize(List<IfdEntry> entries) => 2u + (uint)entries.Count * 12u + 4u;

    private static uint ExtraDataSize(List<IfdEntry> entries)
    {
        uint size = 0;
        foreach (var e in entries)
        {
            if (e.Data.Length > 4)
                size += (uint)((e.Data.Length + 1) & ~1);
        }
        return size;
    }

    private static void WriteIfdWithData(Stream ms, List<IfdEntry> entries, uint ifdOffset)
    {
        // Pad to ifdOffset if needed
        while (ms.Length < ifdOffset)
            ms.WriteByte(0);
        ms.Position = ifdOffset;

        var dataStart = ifdOffset + IfdBlockSize(entries);
        var cursor = dataStart;

        WriteU16(ms, (ushort)entries.Count);
        foreach (var e in entries)
        {
            WriteU16(ms, e.Tag);
            WriteU16(ms, (ushort)e.Type);
            WriteU32(ms, e.Count);
            if (e.Data.Length <= 4)
            {
                var buf = new byte[4];
                Buffer.BlockCopy(e.Data, 0, buf, 0, e.Data.Length);
                ms.Write(buf, 0, 4);
            }
            else
            {
                WriteU32(ms, cursor);
                cursor += (uint)((e.Data.Length + 1) & ~1);
            }
        }
        WriteU32(ms, 0); // next IFD

        foreach (var e in entries)
        {
            if (e.Data.Length <= 4) continue;
            ms.Write(e.Data, 0, e.Data.Length);
            if ((e.Data.Length & 1) == 1)
                ms.WriteByte(0);
        }
    }

    private static string? Get(Dictionary<string, string> map, string key) =>
        map.TryGetValue(key, out var v) ? v : null;

    private static bool TryParseUShort(string? s, out ushort value)
    {
        value = 0;
        return !string.IsNullOrWhiteSpace(s) && ushort.TryParse(s.Trim(), out value);
    }

    private static bool TryParseRational(string? s, out uint num, out uint den)
    {
        num = 0;
        den = 1;
        if (string.IsNullOrWhiteSpace(s)) return false;
        s = s.Trim();
        if (s.Contains('/'))
        {
            var parts = s.Split('/');
            return parts.Length == 2
                   && uint.TryParse(parts[0], out num)
                   && uint.TryParse(parts[1], out den)
                   && den != 0;
        }
        if (double.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out var d))
        {
            // Prefer 1/n for shutter-like values between 0 and 1
            if (d > 0 && d < 1)
            {
                den = (uint)Math.Max(1, Math.Round(1.0 / d));
                num = 1;
                return true;
            }
            den = 1000;
            num = (uint)Math.Max(0, Math.Round(d * den));
            var g = Gcd(num, den);
            num /= g;
            den /= g;
            return true;
        }
        if (uint.TryParse(s, out num))
        {
            den = 1;
            return true;
        }
        return false;
    }

    private static bool TryParseGps(string? s, out (uint n, uint d)[] dms)
    {
        dms = Array.Empty<(uint, uint)>();
        if (string.IsNullOrWhiteSpace(s)) return false;
        s = s.Trim();
        if (s.Contains(','))
        {
            var parts = s.Split(',');
            if (parts.Length != 3) return false;
            dms = new (uint, uint)[3];
            for (var i = 0; i < 3; i++)
            {
                if (!TryParseRational(parts[i], out var n, out var d)) return false;
                dms[i] = (n, d);
            }
            return true;
        }
        if (!double.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out var dec))
            return false;
        dec = Math.Abs(dec);
        var deg = (uint)dec;
        var minF = (dec - deg) * 60.0;
        var min = (uint)minF;
        var sec = (minF - min) * 60.0;
        var secNum = (uint)Math.Round(sec * 100);
        dms = [(deg, 1), (min, 1), (secNum, 100)];
        return true;
    }

    private static uint Gcd(uint a, uint b)
    {
        while (b != 0)
        {
            var t = a % b;
            a = b;
            b = t;
        }
        return a == 0 ? 1 : a;
    }

    private static void WriteU16(Stream s, ushort v)
    {
        Span<byte> b = stackalloc byte[2];
        BinaryPrimitives.WriteUInt16LittleEndian(b, v);
        s.Write(b);
    }

    private static void WriteU32(Stream s, uint v)
    {
        Span<byte> b = stackalloc byte[4];
        BinaryPrimitives.WriteUInt32LittleEndian(b, v);
        s.Write(b);
    }

    private enum ExifType : ushort
    {
        Byte = 1,
        Ascii = 2,
        Short = 3,
        Long = 4,
        Rational = 5,
        Undefined = 7,
    }

    private sealed class IfdEntry
    {
        public ushort Tag;
        public ExifType Type;
        public uint Count;
        public byte[] Data = Array.Empty<byte>();

        public static IfdEntry Ascii(ushort tag, string value)
        {
            var bytes = Encoding.ASCII.GetBytes(value + "\0");
            return new IfdEntry { Tag = tag, Type = ExifType.Ascii, Count = (uint)bytes.Length, Data = bytes };
        }

        public static IfdEntry Short(ushort tag, ushort value)
        {
            var data = new byte[2];
            BinaryPrimitives.WriteUInt16LittleEndian(data, value);
            return new IfdEntry { Tag = tag, Type = ExifType.Short, Count = 1, Data = data };
        }

        public static IfdEntry Long(ushort tag, uint value)
        {
            var data = new byte[4];
            BinaryPrimitives.WriteUInt32LittleEndian(data, value);
            return new IfdEntry { Tag = tag, Type = ExifType.Long, Count = 1, Data = data };
        }

        public static IfdEntry Byte(ushort tag, byte value) =>
            new() { Tag = tag, Type = ExifType.Byte, Count = 1, Data = [value] };

        public static IfdEntry ByteArray(ushort tag, byte[] values) =>
            new() { Tag = tag, Type = ExifType.Byte, Count = (uint)values.Length, Data = values };

        public static IfdEntry Undefined(ushort tag, byte[] values) =>
            new() { Tag = tag, Type = ExifType.Undefined, Count = (uint)values.Length, Data = values };

        public static IfdEntry Rational(ushort tag, uint num, uint den)
        {
            var data = new byte[8];
            BinaryPrimitives.WriteUInt32LittleEndian(data.AsSpan(0, 4), num);
            BinaryPrimitives.WriteUInt32LittleEndian(data.AsSpan(4, 4), den);
            return new IfdEntry { Tag = tag, Type = ExifType.Rational, Count = 1, Data = data };
        }

        public static IfdEntry GpsRational(ushort tag, (uint n, uint d)[] dms)
        {
            var data = new byte[24];
            for (var i = 0; i < 3; i++)
            {
                BinaryPrimitives.WriteUInt32LittleEndian(data.AsSpan(i * 8, 4), dms[i].n);
                BinaryPrimitives.WriteUInt32LittleEndian(data.AsSpan(i * 8 + 4, 4), dms[i].d);
            }
            return new IfdEntry { Tag = tag, Type = ExifType.Rational, Count = 3, Data = data };
        }
    }
}
