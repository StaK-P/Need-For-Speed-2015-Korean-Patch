using System;
using System.IO;
using System.Linq;
using System.Reflection;
using Frosty.Core.IO;
using Frosty.Core.Mod;
using FrostySdk;
using FrostySdk.Ebx;
using FrostySdk.IO;
class ModLocaleInspection
{
 static Assembly Resolve(object sender,ResolveEventArgs args) {
   if(!args.Name.StartsWith("EbxClasses",StringComparison.OrdinalIgnoreCase))return null;
   var p=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"Profiles","NFS16SDK.dll");
   return File.Exists(p)?Assembly.LoadFrom(p):null;
 }
 static int Main(string[] a) {
  if(a.Length!=1)return 2;
  AppDomain.CurrentDomain.AssemblyResolve+=Resolve;
  ProfilesLibrary.Initialize(new Profile[0]);ProfilesLibrary.Initialize("NFS16");TypeLibrary.Initialize();
  using(var f=File.OpenRead(a[0]))
  using(var mr=new FrostyModReader(f)) {
   mr.ReadModDetails();var resources=mr.ReadResources();
   var res=resources.First(x=>x.Type==ModResourceType.Ebx && x.Name=="localization/textdbs/en_us");
   var comp=mr.GetResourceData(res);
   using(var cr=new CasReader(new MemoryStream(comp))) {
    var dec=cr.Read();Console.WriteLine("EBX_BYTES "+dec.Length);
    using(var er=EbxReader.CreateReader(new MemoryStream(dec))) {
     var obj=er.ReadAsset<EbxAsset>().RootObject;
     foreach(var p in obj.GetType().GetProperties(BindingFlags.Public|BindingFlags.Instance)) {
      if(p.Name.IndexOf("Chunk",StringComparison.OrdinalIgnoreCase)>=0||p.Name=="Language")
       Console.WriteLine(p.Name+"="+p.GetValue(obj,null));
     }
    }
   }
   foreach(var c in resources.Where(x=>x.Type==ModResourceType.Chunk))
    Console.WriteLine("MOD_CHUNK "+c.Name+" SIZE="+c.Size);
  }return 0;
 }
}