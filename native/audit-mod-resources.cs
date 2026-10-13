using System;
using System.IO;
using System.Collections.Generic;
using System.Linq;
using Frosty.Core.IO;
using Frosty.Core.Mod;
using FrostySdk;

internal static class NfsModCompatibilityAudit
{
    private sealed class Hit
    {
        public string Mod;
        public BaseModResource Res;
    }
    private static int Main(string[] args)
    {
        if (args.Length == 0) { Console.Error.WriteLine("Usage: audit-mod-resources.exe <mod directory or .fbmod paths...>"); return 2; }
        ProfilesLibrary.Initialize(new Profile[0]);
        if (!ProfilesLibrary.Initialize("NFS16")) { Console.Error.WriteLine("NFS16 profile missing"); return 2; }
        var files = new SortedSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var a in args)
        {
            if (Directory.Exists(a)) foreach (var f in Directory.GetFiles(a, "*.fbmod", SearchOption.TopDirectoryOnly)) files.Add(f);
            else if (File.Exists(a)) files.Add(a);
        }
        var hits = new Dictionary<string,List<Hit>>(StringComparer.OrdinalIgnoreCase);
        foreach (var f in files)
        {
            try
            {
                using(var stream = File.OpenRead(f))
                using(var reader = new FrostyModReader(stream))
                {
                    if (!reader.IsValid) { Console.WriteLine("INVALID " + Path.GetFileName(f)); continue; }
                    reader.ReadModDetails();
                    var resources = reader.ReadResources();
                    Console.WriteLine("MOD " + Path.GetFileName(f) + " FORMAT=" + reader.Version +
                                      " VERSION=" + reader.GameVersion + " RESOURCES=" + resources.Length);
                    foreach (var r in resources)
                    {
                        if (r.Type == ModResourceType.Embedded || r.Type == ModResourceType.Bundle) continue;
                        var key = r.Type.ToString() + "|" + r.Name.ToLowerInvariant();
                        List<Hit> list;
                        if (!hits.TryGetValue(key,out list)) { list = new List<Hit>(); hits.Add(key,list); }
                        list.Add(new Hit{Mod=Path.GetFileName(f),Res=r});
                        if (r.Name.IndexOf("localization/textdbs/en_us",StringComparison.OrdinalIgnoreCase) >= 0)
                            Console.WriteLine("  EN_US kind="+r.Type+" handler="+r.HasHandler+" handleID="+r.Handler.ToString("X8")+" size="+r.Size);
                    }
                }
            }
            catch(Exception e) { Console.WriteLine("ERROR " + Path.GetFileName(f) + " "+e.ToString()); }
        }
        var conflicts = hits.Where(kv=>kv.Value.Select(v=>v.Mod).Distinct(StringComparer.OrdinalIgnoreCase).Count()>1).ToList();
        Console.WriteLine("COLLISION_ASSETS "+conflicts.Count);
        var korean = conflicts.Where(kv=>kv.Value.Any(h=>h.Mod.IndexOf("Korean",StringComparison.OrdinalIgnoreCase)>=0)).ToList();
        Console.WriteLine("KOREAN_COLLISION_ASSETS "+korean.Count);
        foreach(var kv in korean.OrderBy(k=>k.Key))
        {
            Console.WriteLine("CONFLICT "+kv.Key);
            foreach(var h in kv.Value) Console.WriteLine("    "+h.Mod+" handler="+h.Res.HasHandler);
        }
        foreach(var kv in conflicts.Where(k=>k.Key.IndexOf("localization/",StringComparison.OrdinalIgnoreCase)>=0 && !korean.Contains(k)).Take(20))
            Console.WriteLine("OTHER_LOCALE_CONFLICT "+kv.Key+" mods="+string.Join(";",kv.Value.Select(v=>v.Mod).ToArray()));
        return 0;
    }
}