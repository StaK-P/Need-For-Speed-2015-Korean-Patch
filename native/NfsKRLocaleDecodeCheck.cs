using System;
using System.IO;
using System.Reflection;
using FrostySdk;
using FsLocalizationPlugin;
class NfsKRLocaleDecodeCheck{
 static Assembly Resolve(object sender, ResolveEventArgs args){
  string name=new AssemblyName(args.Name).Name;
  if(name=="FlammenwerferPlugin"||name=="FsLocalizationPlugin"){
   string dll=@"D:\Games\EA\nfs-2015-korean-patch\.external\frosty\modmanager-ko-1.0.6.3\FrostyModManager\Plugins\FlammenwerferPlugin.dll";
   return File.Exists(dll)?Assembly.LoadFrom(dll):null;
  }return null;
 }
 static int Main(string[] args){
  try{
   AppDomain.CurrentDomain.AssemblyResolve+=Resolve;
   if(args.Length!=3)throw new Exception("Usage: NfsKRLocaleDecodeCheck <hist> <bin> <expected count>");
   FsLocalizationPlugin.Helpers.DebugLogHelper.Enabled=false;
   using(var h=File.OpenRead(args[0]))
   using(var b=File.OpenRead(args[1])){
    var x=Flammen.ReadStrings(h,b);
    if(x.Count!=int.Parse(args[2]))throw new Exception("Expected "+args[2]+" strings, got "+x.Count);
    uint key=Convert.ToUInt32("660C5CB2",16);
    if(!x.ContainsKey(key))throw new Exception("Missing title-button ID");
    Console.WriteLine("FLAMMENWERFER_LOCALE_DECODE_PASS "+x.Count+" TITLE_ID="+x[key]);
   }return 0;
  }catch(Exception e){Console.Error.WriteLine(e);return 1;}
 }
}
