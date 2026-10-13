using System;
using System.IO;
using System.Reflection;
using FrostySdk;
using FrostySdk.Ebx;
using FrostySdk.IO;
internal class NfsKREbxRepack {
 static Assembly Resolve(object s, ResolveEventArgs e) {
  if(!e.Name.StartsWith("EbxClasses",StringComparison.OrdinalIgnoreCase))return null;
  var path=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"Profiles","NFS16SDK.dll");
  return File.Exists(path)?Assembly.LoadFrom(path):null;
 }
 static int Main(string[] args) {
  try {
   if(args.Length<4){Console.Error.WriteLine("Usage: NfsKREbxRepack <raw-source-ebx> <new-binarychunk-byte-len> <new-histogramchunk-byte-len> <output-ebx>");return 2;}
   AppDomain.CurrentDomain.AssemblyResolve+=Resolve;
   ProfilesLibrary.Initialize(new Profile[0]);
   if(!ProfilesLibrary.Initialize("NFS16"))throw new Exception("NFS16 Frosty profile unavailable");
   TypeLibrary.Initialize();
   EbxAsset asset;
   using(var f=File.OpenRead(args[0]))
   using(var r=EbxReader.CreateReader(f)) {
    if(!r.IsValid)throw new InvalidDataException("Input is not an EBX file");
    asset=r.ReadAsset<EbxAsset>();
   }
   dynamic obj=asset.RootObject;
   if(obj.GetType().Name!="FsUITextDatabase")throw new InvalidDataException("EBX is not FsUITextDatabase: "+obj.GetType().Name);
   var oldBin=(uint)obj.BinaryChunkSize;
   var oldHist=(uint)obj.HistogramChunkSize;
   Guid binId=(Guid)obj.BinaryChunk;
   Guid histId=(Guid)obj.HistogramChunk;
   uint newBin=uint.Parse(args[1]);
   uint newHist=uint.Parse(args[2]);
   if(newBin<128 || newHist<256 || newBin>20000000 || newHist>1000000)throw new Exception("Implausible locale chunk byte sizes");
   obj.BinaryChunkSize=newBin;
   obj.HistogramChunkSize=newHist;
   byte[] output;
   using(var w=EbxBaseWriter.CreateWriter(new MemoryStream())) {
    w.WriteAsset(asset);
    output=w.ToByteArray();
   }
   // Read the freshly produced EBX, ensure original chunk links and new sizes.
   using(var r=EbxReader.CreateReader(new MemoryStream(output))) {
    if(!r.IsValid)throw new InvalidDataException("Output EBX unreadable");
    dynamic check=r.ReadAsset<EbxAsset>().RootObject;
    if((uint)check.BinaryChunkSize!=newBin || (uint)check.HistogramChunkSize!=newHist
       || (Guid)check.BinaryChunk!=binId || (Guid)check.HistogramChunk!=histId)
       throw new InvalidDataException("EBX round-trip validation failed");
   }
   if(File.Exists(args[3]))throw new IOException("Refusing to overwrite EBX output");
   File.WriteAllBytes(args[3],output);
   Console.WriteLine("NFSKR_EBX_ROUNDTRIP_PASS old="+oldBin+","+oldHist+" new="+newBin+","+newHist+" in="+new FileInfo(args[0]).Length+" out="+output.Length+" chunk="+binId+" hist="+histId);
   return 0;
  }catch(Exception e){Console.Error.WriteLine("NFSKR_EBX_REPACK_FAILED "+e);return 1;}
 }
}
