using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using FrostySdk;
using FrostySdk.Ebx;
using FrostySdk.Interfaces;
using FrostySdk.IO;
using FrostySdk.Managers;

// Read-only NFS 2015 localization inspector. Outputs are intentionally kept out of Git.
// Requires Frosty 1.0.6.3 files and a legitimately installed NFS 2015.
internal static class NfsLocaleDump
{
    private sealed class Logger : ILogger
    {
        public void Log(string message, params object[] args)
        {
            // Frosty prints many thousands of percentage updates during the first index build.
            if (message.StartsWith("progress:", StringComparison.OrdinalIgnoreCase) ||
                message.StartsWith("Initial load - Indexing data", StringComparison.OrdinalIgnoreCase)) return;
            Console.WriteLine("[Frosty] " + string.Format(message, args));
        }
        public void LogWarning(string message, params object[] args) { Console.WriteLine("[Warning] " + string.Format(message, args)); }
        public void LogError(string message, params object[] args) { Console.Error.WriteLine("[Error] " + string.Format(message, args)); }
    }

    private static int Main(string[] args)
    {
        try
        {
            AppDomain.CurrentDomain.AssemblyResolve += ResolveAssembly;
            ProfilesLibrary.Initialize(new Profile[0]);
            if (!ProfilesLibrary.Initialize("NFS16"))
                throw new InvalidOperationException("Frosty NFS16 profile is unavailable.");
            Console.WriteLine("PROFILE " + ProfilesLibrary.ProfileName + " version=" + ProfilesLibrary.DataVersion +
                              " sdk=" + ProfilesLibrary.SDKFilename + " requires_key=" + ProfilesLibrary.RequiresKey);
            if (args.Length == 1 && args[0] == "--profile")
            {
                foreach (FileSystemSource source in ProfilesLibrary.Sources)
                    Console.WriteLine("SOURCE " + source.Path + " recursively=" + source.SubDirs);
                return 0;
            }
            if (args.Length != 2 && args.Length != 3)
            {
                Console.Error.WriteLine("Usage: NfsLocaleDump.exe <game_directory> <output_csv> [language name, e.g. English/German/Japanese]");
                Console.Error.WriteLine("       NfsLocaleDump.exe --profile");
                return 2;
            }
            string gamePath = Path.GetFullPath(args[0]);
            string output = Path.GetFullPath(args[1]);
            string targetLanguage = args.Length == 3 ? args[2] : "English";
            if (!File.Exists(Path.Combine(gamePath, "NFS16.exe")))
                throw new FileNotFoundException("NFS16.exe not found", gamePath);
            Directory.CreateDirectory("Caches");
            if (ProfilesLibrary.RequiresKey)
                throw new InvalidOperationException("Profile needs a game key. Do not attempt DRM bypass. Use official tools instead.");
            TypeLibrary.Initialize();
            Console.WriteLine("SDK_VERSION " + TypeLibrary.GetSdkVersion());
            var fs = new FrostySdk.FileSystem(gamePath);
            foreach (FileSystemSource src in ProfilesLibrary.Sources)
                fs.AddSource(src.Path, src.SubDirs);
            fs.Initialize();
            Console.WriteLine("FILESYSTEM_HEAD " + fs.Head);
            var rm = new ResourceManager(fs);
            rm.SetLogger(new Logger());
            rm.Initialize();
            var am = new AssetManager(fs, rm);
            am.SetLogger(new Logger());
            Console.WriteLine("ASSET_INDEX_START");
            am.Initialize(true);
            Console.WriteLine("ASSET_INDEX_FINISHED");
            InspectFontAssets(am, Path.Combine(Path.GetDirectoryName(output), "font-asset-inventory.csv"));
            InspectFontBindings(am, Path.Combine(Path.GetDirectoryName(output), "font-style-bindings.txt"));
            InspectFontConsumers(am, Path.Combine(Path.GetDirectoryName(output), "font-style-consumers.txt"));
            var unique = new SortedDictionary<uint, string>();
            int assetCount = 0;
            int matchCount = 0;
            foreach (EbxAssetEntry entry in am.EnumerateEbx("LocalizationAsset"))
            {
                assetCount++;
                dynamic localizationAsset = am.GetEbx(entry).RootObject;
                foreach (PointerRef pointer in localizationAsset.LocalizedTexts)
                {
                    EbxAssetEntry localizedEntry = am.GetEbxEntry(pointer.External.FileGuid);
                    if (localizedEntry == null) continue;
                    dynamic localizedText = am.GetEbx(localizedEntry).RootObject;
                    if (localizedText.Language.ToString() != "LanguageFormat_" + targetLanguage) continue;
                    Guid binaryChunk = localizedText.BinaryChunk;
                    Guid histogramChunk = localizedText.HistogramChunk;
                    ChunkAssetEntry binaryEntry = am.GetChunkEntry(binaryChunk);
                    ChunkAssetEntry histEntry = am.GetChunkEntry(histogramChunk);
                    if (binaryEntry == null || histEntry == null)
                    {
                        Console.WriteLine("MISSING_CHUNKS " + localizedEntry.Name);
                        continue;
                    }
                    Console.WriteLine("FOUND_LANGUAGE=" + targetLanguage + " " + localizedEntry.Name + " type=" + localizedEntry.Type);
                    Type textType = TypeLibrary.GetType(localizedEntry.Type);
                    Console.WriteLine("LOCALE_TYPE_BASE " + (textType == null ? "null" : textType.BaseType.FullName));
                    matchCount++;
                    ReadStrings(am, binaryEntry, histEntry, unique);
                }
            }
            Console.WriteLine("LOCALE_ASSETS " + assetCount + " ENGLISH_ASSETS " + matchCount + " STRINGS " + unique.Count);
            if (unique.Count == 0) throw new InvalidDataException("No localized strings extracted.");
            Directory.CreateDirectory(Path.GetDirectoryName(output));
            using (var writer = new StreamWriter(output, false, new UTF8Encoding(true)))
            {
                writer.WriteLine("string_id,source_text");
                foreach (var item in unique)
                    writer.WriteLine(Csv(item.Key.ToString("X8")) + "," + Csv(item.Value));
            }
            Console.WriteLine("WROTE " + output);
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine("FATAL " + error);
            return 1;
        }
    }

    private static Assembly ResolveAssembly(object sender, ResolveEventArgs args)
    {
        if (!args.Name.StartsWith("EbxClasses", StringComparison.OrdinalIgnoreCase))
            return null;
        string path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Profiles", "NFS16SDK.dll");
        return File.Exists(path) ? Assembly.LoadFrom(path) : null;
    }

    private static void ReadStrings(AssetManager am, ChunkAssetEntry binaryEntry, ChunkAssetEntry histEntry,
                                    IDictionary<uint, string> destination)
    {
        List<ushort> histogram = new List<ushort>();
        using (NativeReader hist = new NativeReader(am.GetChunk(histEntry)))
        {
            hist.ReadUInt();
            uint numBytes = hist.ReadUInt();
            hist.ReadUInt();
            if (numBytes > 1024 * 1024 || (numBytes % 2) != 0)
                throw new InvalidDataException("Unexpected localization histogram size: " + numBytes);
            for (int i = 0; i < numBytes / 2; i++) histogram.Add(hist.ReadUShort());
        }
        int hangulChars = histogram.Count(ch => ch >= 0xAC00 && ch <= 0xD7A3);
        Console.WriteLine("HISTOGRAM entries=" + histogram.Count + " HangulSyllables=" + hangulChars);
        using (NativeReader data = new NativeReader(am.GetChunk(binaryEntry)))
        {
            uint magic = data.ReadUInt();
            if (magic != 0x00039000) throw new InvalidDataException("Unexpected localization magic: " + magic.ToString("X8"));
            data.ReadUInt();
            int count = data.ReadInt();
            uint tableOffset = data.ReadUInt();
            uint stringsOffset = data.ReadUInt();
            string tag = data.ReadNullTerminatedString();
            if (count < 0 || count > 2000000 ||
                (ulong)tableOffset + 8ul + (ulong)count * 8ul > (ulong)data.Length ||
                (ulong)stringsOffset + 8ul > (ulong)data.Length)
                throw new InvalidDataException("Invalid localization table bounds");
            data.Position = tableOffset + 8;
            uint[] ids = new uint[count];
            uint[] offsets = new uint[count];
            for (int i = 0; i < count; i++)
            {
                ids[i] = data.ReadUInt();
                offsets[i] = data.ReadUInt();
            }
            for (int i = 0; i < count; i++)
            {
                long position = (long)stringsOffset + offsets[i] + 8L;
                if (position < 0 || position >= data.Length)
                    throw new InvalidDataException("String offset out of range for ID " + ids[i].ToString("X8"));
                data.Position = position;
                string raw = data.ReadNullTerminatedString();
                var decoded = new StringBuilder(raw.Length);
                for (int k = 0; k < raw.Length; k++)
                {
                    byte b = unchecked((byte)raw[k]);
                    if (b < 0x80) decoded.Append((char)b);
                    else
                    {
                        if (b >= histogram.Count) throw new InvalidDataException("Histogram index out of range");
                        ushort value = histogram[b];
                        if (value >= 0x80) decoded.Append((char)value);
                        else if (++k < raw.Length)
                        {
                            byte next = unchecked((byte)raw[k]);
                            if (next >= 0x80)
                            {
                                int index = (next - 0x80) + (value << 7);
                                if (index < histogram.Count) decoded.Append((char)histogram[index]);
                                else throw new InvalidDataException("Shifted histogram index out of range");
                            }
                            else throw new InvalidDataException("Invalid shifted character");
                        }
                        else throw new InvalidDataException("Missing shifted character");
                    }
                }
                if (!destination.ContainsKey(ids[i]))
                    destination.Add(ids[i], decoded.ToString());
            }
            Console.WriteLine("CHUNK " + tag + " entries=" + count + " total_unique=" + destination.Count);
        }
    }

    private static void InspectFontConsumers(AssetManager am, string destination)
    {
        var styleByGuid = new Dictionary<Guid, string>();
        var consumers = new SortedDictionary<string, List<string>>(StringComparer.OrdinalIgnoreCase);
        foreach (EbxAssetEntry fontStyle in am.EnumerateEbx("UIElementFontStyle"))
        {
            styleByGuid[fontStyle.Guid] = fontStyle.Name;
            consumers[fontStyle.Name] = new List<string>();
        }
        int matchedEdges = 0;
        foreach (EbxAssetEntry asset in am.EnumerateEbx())
        {
            foreach (Guid dependent in asset.DependentAssets)
            {
                string fontStyle;
                if (styleByGuid.TryGetValue(dependent, out fontStyle))
                {
                    consumers[fontStyle].Add(asset.Name + " (" + asset.Type + ")");
                    matchedEdges++;
                }
            }
        }
        using (var writer = new StreamWriter(destination, false, new UTF8Encoding(true)))
        {
            foreach (var pair in consumers)
            {
                writer.WriteLine("FONT_STYLE " + pair.Key + " USES=" + pair.Value.Count);
                foreach (string consumer in pair.Value.OrderBy(x => x).Take(90))
                    writer.WriteLine("  " + consumer);
                if (pair.Value.Count > 90) writer.WriteLine("  (more consumers omitted)");
            }
        }
        Console.WriteLine("FONT_STYLE_USAGE " + consumers.Count + " styles matched_edges=" + matchedEdges);
    }

    private static void InspectFontBindings(AssetManager am, string destination)
    {
        int total = 0;
        using (var writer = new StreamWriter(destination, false, new UTF8Encoding(true)))
        {
            foreach (EbxAssetEntry entry in am.EnumerateEbx())
            {
                if (entry.Type != "UIElementFontStyle" &&
                    entry.Type != "UITtfAsset" &&
                    entry.Type != "UIImmediateModeFontConfigurationAsset")
                    continue;
                total++;
                writer.WriteLine("ASSET " + entry.Name + " TYPE=" + entry.Type);
                try
                {
                    object obj = am.GetEbx(entry).RootObject;
                    if (obj != null)
                    {
                        Type cls = obj.GetType();
                        foreach (var property in cls.GetProperties(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance))
                        {
                            if (!property.CanRead || property.GetIndexParameters().Length != 0) continue;
                            try
                            {
                                object val = property.GetValue(obj, null);
                                writer.WriteLine("  PROPERTY " + property.Name + " : " +
                                                 property.PropertyType.Name + " = " + AssetValue(val));
                                if (property.Name == "Hd" || property.Name == "LanguageOverrides" ||
                                    property.Name == "FontBundles" || property.Name == "FontFile")
                                    DumpFontSubMembers(writer, "    ", val, 0);
                            }
                            catch (Exception ex) { writer.WriteLine("  PROPERTY " + property.Name + " ERROR " + ex.Message); }
                        }
                        foreach (var field in cls.GetFields(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance))
                        {
                            object val = field.GetValue(obj);
                            writer.WriteLine("  FIELD " + field.Name + " : " + field.FieldType.Name +
                                             " = " + AssetValue(val));
                        }
                    }
                }
                catch (Exception ex) { writer.WriteLine("  ASSET_ERROR " + ex.ToString()); }
                writer.WriteLine("");
            }
        }
        Console.WriteLine("FONT_STYLE_BINDINGS " + total + " file=" + destination);
    }

    private static void DumpFontSubMembers(StreamWriter writer, string indent, object value, int depth)
    {
        if (value == null || depth > 3) return;
        if (value is PointerRef)
        {
            PointerRef ptr = (PointerRef)value;
            value = ptr.Internal;
            if (value == null) return;
        }
        if (value is System.Collections.IEnumerable && !(value is string))
        {
            int index = 0;
            foreach (object child in (System.Collections.IEnumerable)value)
            {
                if (index >= 8) { writer.WriteLine(indent + "(remaining entries omitted)"); break; }
                writer.WriteLine(indent + "ITEM[" + index + "] " + AssetValue(child));
                DumpFontSubMembers(writer, indent + "  ", child, depth + 1);
                index++;
            }
            return;
        }
        if (value is string || value.GetType().IsPrimitive || value.GetType().IsEnum) return;
        var properties = value.GetType().GetProperties(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
        foreach (var property in properties)
        {
            if (!property.CanRead || property.GetIndexParameters().Length != 0 ||
                property.Name.StartsWith("__", StringComparison.OrdinalIgnoreCase)) continue;
            try
            {
                object inner = property.GetValue(value, null);
                writer.WriteLine(indent + property.Name + ": " + AssetValue(inner));
                if (inner != null && depth < 3 &&
                    (inner is PointerRef || property.Name == "FontDefinition" ||
                     property.Name == "Definition" || property.Name == "Font" ||
                     property.Name == "FontLookup" || property.Name == "TtfAssets"))
                    DumpFontSubMembers(writer, indent + "  ", inner, depth + 1);
            }
            catch (Exception e) { writer.WriteLine(indent + property.Name + ": ERROR " + e.Message); }
        }
    }

    private static string AssetValue(object value)
    {
        if (value == null) return "null";
        if (value is PointerRef)
        {
            PointerRef ptr = (PointerRef)value;
            return "PointerRef externalFileGuid=" + ptr.External.FileGuid +
                   " internal=" + ptr.Internal;
        }
        if (value is string || value.GetType().IsPrimitive || value is Guid || value.GetType().IsEnum)
            return value.ToString();
        if (value is System.Collections.IEnumerable) return "ENUMERABLE " + value.GetType().FullName;
        return value.ToString();
    }

    private static void InspectFontAssets(AssetManager am, string destination)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(destination));
        string fontOutputDir = Path.Combine(Path.GetDirectoryName(destination), "font-files");
        Directory.CreateDirectory(fontOutputDir);
        int found = 0;
        using (var writer = new StreamWriter(destination, false, new UTF8Encoding(true)))
        {
            writer.WriteLine("asset_kind,name,type,original_size");
            foreach (ResAssetEntry item in am.EnumerateRes())
            {
                string name = item.Name ?? "";
                string type = item.Type ?? "";
                if (name.IndexOf("font", StringComparison.OrdinalIgnoreCase) < 0 &&
                    type.IndexOf("font", StringComparison.OrdinalIgnoreCase) < 0) continue;
                writer.WriteLine("res," + Csv(name) + "," + Csv(type) + "," + item.OriginalSize);
                found++;
                if (item.ResType == (uint)ResourceType.UITtfFontFile)
                {
                    // Only local analysis: never commit extracted EA font binaries.
                    string fileName = name.Replace('/', '_').Replace('\\', '_') + ".bin";
                    string path = Path.Combine(fontOutputDir, fileName);
                    using (Stream source = am.GetRes(item))
                    using (FileStream output = File.Create(path))
                        source.CopyTo(output);
                    Console.WriteLine("EXTRACTED_LOCAL_FONT " + fileName);
                }
            }
            foreach (EbxAssetEntry item in am.EnumerateEbx())
            {
                string name = item.Name ?? "";
                string type = item.Type ?? "";
                if (name.IndexOf("font", StringComparison.OrdinalIgnoreCase) < 0 &&
                    type.IndexOf("font", StringComparison.OrdinalIgnoreCase) < 0) continue;
                writer.WriteLine("ebx," + Csv(name) + "," + Csv(type) + "," + item.OriginalSize);
                found++;
            }
        }
        Console.WriteLine("FONT_ASSET_CANDIDATES " + found + " file=" + destination);
    }

    private static string Csv(string input)
    {
        return "\"" + (input ?? "").Replace("\"", "\"\"") + "\"";
    }
}
