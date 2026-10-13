using System;
using System.IO;
using System.Text;
using System.Collections.Generic;
using System.Globalization;
class NfsKRNativeLocaleCheck
{
 static byte[] ReadExactly(BinaryReader reader,int length)
 {
  byte[] data=reader.ReadBytes(length);
  if(data.Length!=length)throw new InvalidDataException("Truncated locale content");
  return data;
 }
 static int Main(string[] args)
 {
  try
  {
   if(args.Length!=3)throw new ArgumentException("Usage: NfsKRNativeLocaleCheck.exe <histogram> <strings-binary> <expected-count>");
   var h=File.ReadAllBytes(args[0]); var b=File.ReadAllBytes(args[1]);
   if(h.Length<12||BitConverter.ToUInt32(h,0)!=0x39001)
    throw new InvalidDataException("Invalid NFS16 histogram");
   int countHist=(h.Length-12)/2;
   var histogram=new ushort[countHist];
   for(int i=0;i<countHist;i++)histogram[i]=BitConverter.ToUInt16(h,12+i*2);
   if(b.Length<148||BitConverter.ToUInt32(b,0)!=0x39000)
    throw new InvalidDataException("Invalid NFS16 binary chunk");
   int n=BitConverter.ToInt32(b,8);
   uint idx=BitConverter.ToUInt32(b,12);
   uint start=BitConverter.ToUInt32(b,16);
   if(n<0||n>300000||idx<20||idx+(ulong)(n*8)>start||start+8>=b.Length)
    throw new InvalidDataException("Invalid binary string index");
   var result=new Dictionary<uint,string>(n);
   for(int i=0;i<n;i++)
   {
    int offset=(int)idx+8+i*8;
    uint key=BitConverter.ToUInt32(b,offset);
    uint from=BitConverter.ToUInt32(b,offset+4);
    long pos=(long)start+8+from;
    if(pos>=b.Length||pos<0)throw new InvalidDataException("String offset invalid");
    var text=new StringBuilder();
    bool terminated=false;
    while(pos<b.Length)
    {
     byte c=b[pos++];
     if(c==0){terminated=true;break;}
     if(c<128){text.Append((char)c);continue;}
     if(c>=histogram.Length)throw new InvalidDataException("Histogram index invalid");
     ushort ch=histogram[c];
     if(ch<128)
     {
      if(pos>=b.Length||b[pos]<128)throw new InvalidDataException("Shifted char missing");
      int codeIndex=(int)ch*128+b[pos++]-128;
      if(codeIndex>=histogram.Length)throw new InvalidDataException("Shift out of bounds");
      ch=histogram[codeIndex];
     }
     text.Append((char)ch);
    }
    if(!terminated||result.ContainsKey(key))throw new InvalidDataException("Missing NUL / duplicate string ID");
    result.Add(key,text.ToString());
   }
   if(result.Count!=int.Parse(args[2],CultureInfo.InvariantCulture))
    throw new InvalidDataException("String count mismatch");
   uint title=0x660C5CB2;
   if(!result.ContainsKey(title)||!result[title].Contains("계속"))throw new InvalidDataException("Korean title hint missing");
   Console.WriteLine("NFSKR_NATIVE_LOCALE_DECODE_PASS count="+result.Count+" title="+result[title]);
   return 0;
  }catch(Exception e){Console.Error.WriteLine("NFSKR_NATIVE_LOCALE_INVALID "+e.ToString());return 1;}
 }
}
