namespace EXIFexit.Infrastructure.Imaging;

/// <summary>
/// Low-level JPEG marker walker for lossless metadata strip / APP1 replace.
/// Does not re-encode image scan data.
/// </summary>
public static class JpegSegmentEditor
{
    private static readonly byte[] ExifHeader = "Exif\0\0"u8.ToArray();
    private static readonly byte[] XmpHeader = "http://ns.adobe.com/xap/1.0/\0"u8.ToArray();

    public static bool IsJpeg(ReadOnlySpan<byte> data) =>
        data.Length >= 2 && data[0] == 0xFF && data[1] == 0xD8;

    public static byte[] StripMetadata(byte[] jpeg, bool keepIcc = false)
    {
        if (!IsJpeg(jpeg))
            throw new InvalidDataException("Not a JPEG file");

        using var input = new MemoryStream(jpeg);
        using var output = new MemoryStream(jpeg.Length);
        output.WriteByte(0xFF);
        output.WriteByte(0xD8);
        input.Position = 2;

        while (input.Position < input.Length)
        {
            var b0 = input.ReadByte();
            if (b0 < 0) break;
            if (b0 != 0xFF)
            {
                // Entropy-coded data without marker — copy rest (shouldn't happen before SOS properly)
                output.WriteByte((byte)b0);
                input.CopyTo(output);
                break;
            }

            int marker;
            do
            {
                marker = input.ReadByte();
            } while (marker == 0xFF);

            if (marker < 0)
                break;

            // Standalone markers
            if (marker == 0xD9) // EOI
            {
                output.WriteByte(0xFF);
                output.WriteByte((byte)marker);
                break;
            }

            if (marker == 0xDA) // SOS — copy rest of file including scan
            {
                output.WriteByte(0xFF);
                output.WriteByte((byte)marker);
                input.CopyTo(output);
                break;
            }

            if (marker >= 0xD0 && marker <= 0xD7) // RSTn
            {
                output.WriteByte(0xFF);
                output.WriteByte((byte)marker);
                continue;
            }

            if (marker == 0x01) // TEM
            {
                output.WriteByte(0xFF);
                output.WriteByte((byte)marker);
                continue;
            }

            // Segment with length
            var lenHi = input.ReadByte();
            var lenLo = input.ReadByte();
            if (lenHi < 0 || lenLo < 0)
                break;
            var length = (lenHi << 8) | lenLo;
            if (length < 2)
                throw new InvalidDataException("Invalid JPEG segment length");
            var payloadLen = length - 2;
            var payload = new byte[payloadLen];
            var read = input.Read(payload, 0, payloadLen);
            if (read != payloadLen)
                throw new InvalidDataException("Truncated JPEG segment");

            if (ShouldStrip((byte)marker, payload, keepIcc))
                continue;

            output.WriteByte(0xFF);
            output.WriteByte((byte)marker);
            output.WriteByte((byte)lenHi);
            output.WriteByte((byte)lenLo);
            output.Write(payload, 0, payload.Length);
        }

        return output.ToArray();
    }

    /// <summary>
    /// Replace or insert EXIF APP1 segment without re-encoding pixels.
    /// <paramref name="exifApp1Payload"/> is the full APP1 payload (including "Exif\0\0" header + TIFF).
    /// </summary>
    public static byte[] UpsertExifApp1(byte[] jpeg, byte[] exifApp1Payload)
    {
        if (!IsJpeg(jpeg))
            throw new InvalidDataException("Not a JPEG file");
        if (exifApp1Payload.Length < 6)
            throw new ArgumentException("EXIF APP1 payload too short");

        using var input = new MemoryStream(jpeg);
        using var output = new MemoryStream(jpeg.Length + exifApp1Payload.Length + 16);
        output.WriteByte(0xFF);
        output.WriteByte(0xD8);
        input.Position = 2;

        var inserted = false;

        while (input.Position < input.Length)
        {
            var b0 = input.ReadByte();
            if (b0 < 0) break;
            if (b0 != 0xFF)
            {
                if (!inserted)
                {
                    WriteApp1(output, exifApp1Payload);
                    inserted = true;
                }
                output.WriteByte((byte)b0);
                input.CopyTo(output);
                break;
            }

            int marker;
            do { marker = input.ReadByte(); } while (marker == 0xFF);
            if (marker < 0) break;

            if (marker == 0xD9)
            {
                if (!inserted)
                {
                    WriteApp1(output, exifApp1Payload);
                    inserted = true;
                }
                output.WriteByte(0xFF);
                output.WriteByte((byte)marker);
                break;
            }

            if (marker == 0xDA)
            {
                if (!inserted)
                {
                    WriteApp1(output, exifApp1Payload);
                    inserted = true;
                }
                output.WriteByte(0xFF);
                output.WriteByte((byte)marker);
                input.CopyTo(output);
                break;
            }

            if (marker is >= 0xD0 and <= 0xD7 or 0x01)
            {
                output.WriteByte(0xFF);
                output.WriteByte((byte)marker);
                continue;
            }

            var lenHi = input.ReadByte();
            var lenLo = input.ReadByte();
            if (lenHi < 0 || lenLo < 0) break;
            var length = (lenHi << 8) | lenLo;
            var payloadLen = length - 2;
            var payload = new byte[payloadLen];
            if (input.Read(payload, 0, payloadLen) != payloadLen)
                throw new InvalidDataException("Truncated JPEG segment");

            // Drop existing EXIF APP1; keep XMP/others
            if (marker == 0xE1 && IsExifApp1(payload))
            {
                if (!inserted)
                {
                    WriteApp1(output, exifApp1Payload);
                    inserted = true;
                }
                continue;
            }

            // Prefer insert right after SOI / JFIF APP0
            if (!inserted && marker != 0xE0)
            {
                WriteApp1(output, exifApp1Payload);
                inserted = true;
            }

            output.WriteByte(0xFF);
            output.WriteByte((byte)marker);
            output.WriteByte((byte)lenHi);
            output.WriteByte((byte)lenLo);
            output.Write(payload, 0, payload.Length);
        }

        if (!inserted)
            WriteApp1(output, exifApp1Payload);

        return output.ToArray();
    }

    private static void WriteApp1(Stream output, byte[] payload)
    {
        var length = payload.Length + 2;
        if (length > 0xFFFF)
            throw new InvalidOperationException("EXIF segment too large for JPEG APP1");
        output.WriteByte(0xFF);
        output.WriteByte(0xE1);
        output.WriteByte((byte)(length >> 8));
        output.WriteByte((byte)(length & 0xFF));
        output.Write(payload, 0, payload.Length);
    }

    private static bool ShouldStrip(byte marker, byte[] payload, bool keepIcc)
    {
        // COM
        if (marker == 0xFE) return true;
        // APP1 EXIF or XMP
        if (marker == 0xE1)
            return IsExifApp1(payload) || IsXmpApp1(payload);
        // APP13 Photoshop IRB (often IPTC)
        if (marker == 0xED) return true;
        // APP2 ICC
        if (marker == 0xE2 && !keepIcc && StartsWith(payload, "ICC_PROFILE\0"u8))
            return true;
        return false;
    }

    private static bool IsExifApp1(byte[] payload) => StartsWith(payload, ExifHeader);
    private static bool IsXmpApp1(byte[] payload) => StartsWith(payload, XmpHeader);

    private static bool StartsWith(byte[] data, ReadOnlySpan<byte> prefix)
    {
        if (data.Length < prefix.Length) return false;
        return data.AsSpan(0, prefix.Length).SequenceEqual(prefix);
    }
}
