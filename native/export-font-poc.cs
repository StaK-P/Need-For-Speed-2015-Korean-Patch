using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using FrostySdk;
using FrostySdk.Ebx;
using FrostySdk.Interfaces;
using FrostySdk.IO;
using FrostySdk.Managers;

internal static class ExportNfs16FontPocAssets
{
    private sealed class Logger : ILogger
    {
        public void Log(string text, params object[] args)
        {
            if (text.StartsWith("progress:") || text.StartsWith("Initial load -")) return;
            Console.WriteLine("[Frosty] " + string.Format(text, args));
        }
        public void LogWarning(string text, params object[] args) { Console.WriteLine("WARNING " + string.Format(text, args)); }
        public void LogError(string text, params object[] args) { Console.Error.WriteLine("ERROR " + string.Format(text, args)); }
    }

    private sealed class FontChange
    {
        public readonly string Asset;
        public readonly string Source;
        public readonly string Family;
        public FontChange(string asset, string source, string family)
        {
            Asset = asset; Source = source; Family = family;
        }
    }

    private static int Main(string[] args)
    {
        try
        {
            if (args.Length != 3 && args.Length != 4)
            {
                Console.Error.WriteLine("Usage: ExportNfs16FontPocAssets.exe <game-dir> <project-root> <output-dir> [local-hybrid-font-dir]");
                return 2;
            }
            AppDomain.CurrentDomain.AssemblyResolve += ResolveAssembly;
            ProfilesLibrary.Initialize(new Profile[0]);
            if (!ProfilesLibrary.Initialize("NFS16")) throw new InvalidDataException("NFS16 Frosty profile missing");
            if (ProfilesLibrary.RequiresKey) throw new InvalidOperationException("Game requires encrypted key, cannot continue");
            TypeLibrary.Initialize();
            string game = Path.GetFullPath(args[0]);
            string project = Path.GetFullPath(args[1]);
            string output = Path.GetFullPath(args[2]);
            bool hybrid = args.Length == 4;
            string hybridDir = hybrid ? Path.GetFullPath(args[3]) : null;
            if (hybrid && !Directory.Exists(hybridDir)) throw new DirectoryNotFoundException(hybridDir);
            if (!File.Exists(Path.Combine(game, "NFS16.exe"))) throw new FileNotFoundException("Game exe not found");
            Directory.CreateDirectory(output);
            Directory.CreateDirectory("Caches");
            var filesystem = new FrostySdk.FileSystem(game);
            foreach (FileSystemSource source in ProfilesLibrary.Sources)
                filesystem.AddSource(source.Path, source.SubDirs);
            filesystem.Initialize();
            var logger = new Logger();
            var resources = new ResourceManager(filesystem);
            resources.SetLogger(logger);
            resources.Initialize();
            var assets = new AssetManager(filesystem, resources);
            assets.SetLogger(logger);
            assets.Initialize(true);
            Console.WriteLine("GAME_HEAD " + filesystem.Head);
            if (filesystem.Head != 366510) throw new InvalidDataException("Unexpected NFS16 patch version");

            var fonts = new FontChange[]
            {
                new FontChange("ui/fonts/dinoffcpro-cond",
                    hybrid ? Path.Combine(hybridDir, "nfs16-din-cond-ko-local.ttf") :
                    Path.Combine(project, @".external\fonts\derived\NFSKR-UI-Text-SemiBold.ttf"), "NFSKR UI Text"),
                new FontChange("ui/fonts/dinoffcpro-condmedi",
                    hybrid ? Path.Combine(hybridDir, "nfs16-din-condmedi-ko-local.ttf") :
                    Path.Combine(project, @".external\fonts\vendor\SUIT-Medium.ttf"), "SUIT"),
                new FontChange("ui/fonts/dinoffcpro-condbold",
                    hybrid ? Path.Combine(hybridDir, "nfs16-din-condbold-ko-local.ttf") :
                    Path.Combine(project, @".external\fonts\vendor\SUITE-Heavy.ttf"), "SUITE")
            };

            var assetsManifest = Path.Combine(output, "font-assets.tsv");
            // Write manifest last, so a failed run cannot leave a false success marker.
            var lines = new List<string>();
            foreach (FontChange font in fonts)
            {
                var resourceEntry = assets.GetResEntry(font.Asset);
                var assetEntry = assets.GetEbxEntry(font.Asset);
                if (resourceEntry == null || assetEntry == null)
                    throw new FileNotFoundException("Required font asset not indexed: " + font.Asset);
                if (resourceEntry.ResType != (uint)ResourceType.UITtfFontFile)
                    throw new InvalidDataException("Unexpected font resource type " + resourceEntry.ResType);
                byte[] raw = File.ReadAllBytes(font.Source);
                if (raw.Length < 100000 || raw[0] != 0 || raw[1] != 1 || raw[2] != 0 || raw[3] != 0)
                    throw new InvalidDataException("TTF source invalid " + font.Source);
                byte[] compressed = Utils.CompressFile(raw, resType: ResourceType.UITtfFontFile);
                string file = Path.Combine(output, Path.GetFileName(font.Source) + ".rescomp");
                File.WriteAllBytes(file, compressed);
                lines.Add(string.Join("\t", new string[] {
                    "res",font.Asset,((uint)resourceEntry.ResType).ToString(),resourceEntry.ResRid.ToString(),
                    Convert.ToBase64String(resourceEntry.ResMeta ?? new byte[0]),
                    raw.Length.ToString(),file
                }));
                Console.WriteLine("RES_FONT " + font.Asset + " ttf=" + raw.Length +
                                  " compressed=" + compressed.Length + " rid=" + resourceEntry.ResRid);
                EbxAsset ebxAsset = assets.GetEbx(assetEntry);
                object root = ebxAsset.RootObject;
                PropertyInfo prop = root.GetType().GetProperty("FontFamilyName");
                if (prop == null || !prop.CanWrite)
                    throw new InvalidOperationException("FontFamilyName missing in " + font.Asset);
                Console.WriteLine("OLD_FAMILY " + prop.GetValue(root, null).ToString());
                if (hybrid)
                {
                    // Composite uses exactly the original DIN family name. No EBX change needed.
                    Console.WriteLine("PRESERVED_ORIGINAL_FONT_EBX " + font.Asset);
                }
                else
                {
                    prop.SetValue(root, (CString)font.Family, null);
                    SaveEbx(ebxAsset, font.Asset, output, lines);
                }
            }

            // Hybrid PoC preserves ALL native font style assignments, including PLAY.
            // Legacy PoC used a font remap that altered English glyph appearance.
            if (!hybrid) foreach (string style in new [] {
                "UI/Fonts/DINPro-Cond-170",
                "UI/Fonts/DINPro-Medium-Cond-170",
                "UI/Fonts/DINPro-Cond-96",
                "UI/Fonts/DINPro-Medium-Cond-96"
            })
            {
                EbxAssetEntry entry = assets.GetEbxEntry(style);
                if (entry == null) throw new InvalidDataException("Style not found " + style);
                EbxAsset ebx = assets.GetEbx(entry);
                object obj = ebx.RootObject;
                PointerRef pref = (PointerRef)obj.GetType().GetProperty("Hd").GetValue(obj,null);
                object definition = pref.Internal;
                if (definition == null) throw new InvalidDataException("Missing HD font definition " + style);
                var lookup = definition.GetType().GetProperty("FontLookup").GetValue(definition, null) as IEnumerable;
                if (lookup == null) throw new InvalidDataException("FontLookup missing " + style);
                int hits = 0;
                foreach (object row in lookup)
                {
                    var rowType = row.GetType();
                    string lang = rowType.GetProperty("Language").GetValue(row,null).ToString();
                    if (lang != "LanguageFormat_English") continue;
                    var target = rowType.GetProperty("FontAssetPath");
                    if (target == null || !target.CanWrite)
                        throw new InvalidDataException("Cannot write font path " + style);
                    Console.WriteLine("STYLE_REMAP " + style + " " + target.GetValue(row,null) +
                                      " => UI/Fonts/DINOffcPro-CondBold");
                    target.SetValue(row, (CString)"UI/Fonts/DINOffcPro-CondBold", null);
                    hits++;
                }
                if (hits != 1) throw new InvalidDataException("Expected one English style lookup: " + style + " actual=" + hits);
                SaveEbx(ebx, style, output, lines);
            }
            if (hybrid && lines.Count != 3) throw new InvalidDataException("Expected three RES-only hybrid font resources");
            File.WriteAllLines(assetsManifest, lines.ToArray(), new UTF8Encoding(false));
            Console.WriteLine("EXPORT_READY assets=" + lines.Count + " manifest=" + assetsManifest);
            return 0;
        }
        catch (Exception e)
        {
            Console.Error.WriteLine("EXPORT_FAILED " + e);
            return 1;
        }
    }

    private static void SaveEbx(EbxAsset asset, string name, string outDir, List<string> lines)
    {
        using (var stream = new MemoryStream())
        using (EbxBaseWriter writer = EbxBaseWriter.CreateWriter(stream))
        {
            writer.WriteAsset(asset);
            byte[] data = writer.ToByteArray();
            if (data.Length < 100) throw new InvalidDataException("Empty serialized EBX");
            byte[] compressed = Utils.CompressFile(data);
            string dest = Path.Combine(outDir, name.Replace('/','_').Replace('\\','_') + ".ebxcomp");
            File.WriteAllBytes(dest, compressed);
            lines.Add(string.Join("\t", new string[] {"ebx",name,"","", "",data.Length.ToString(),dest}));
            Console.WriteLine("EBX_FONT " + name + " raw=" + data.Length + " compressed=" + compressed.Length);
        }
    }

    private static Assembly ResolveAssembly(object sender, ResolveEventArgs args)
    {
        if (!args.Name.StartsWith("EbxClasses", StringComparison.OrdinalIgnoreCase))
            return null;
        string path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Profiles", "NFS16SDK.dll");
        return File.Exists(path) ? Assembly.LoadFrom(path) : null;
    }
}
