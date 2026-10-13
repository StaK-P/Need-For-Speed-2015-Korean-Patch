using System;
using System.IO;
using System.Linq;
using Frosty.Core.IO;
using Frosty.Core.Mod;
using FrostySdk;

class VerifyNfsMod
{
    static int Main(string[] args)
    {
        if (args.Length != 1) { Console.Error.WriteLine("Usage: VerifyNfsMod <mod.fbmod>"); return 2; }
        try
        {
            ProfilesLibrary.Initialize(new Profile[0]);
            if (!ProfilesLibrary.Initialize("NFS16")) throw new InvalidDataException("NFS16 profile missing");
            using (var stream = File.OpenRead(args[0]))
            using (var reader = new FrostyModReader(stream))
            {
                if (!reader.IsValid) throw new InvalidDataException("FrostyModReader.IsValid is false");
                var details = reader.ReadModDetails();
                var resources = reader.ReadResources();
                Console.WriteLine("FROSTY_VALIDATED profile=NFS16 version=" + reader.Version +
                                  " game_version=" + reader.GameVersion);
                Console.WriteLine("RESOURCE_COUNT " + resources.Length);
                int localized = 0;
                foreach (BaseModResource resource in resources)
                {
                    Console.WriteLine("RESOURCE kind=" + resource.Type + " name=" + resource.Name +
                                      " index=" + resource.ResourceIndex + " handler=" +
                                      resource.Handler.ToString("X8") + " size=" + resource.Size);
                    byte[] data = reader.GetResourceData(resource);
                    if (resource.Type == ModResourceType.Ebx && resource.HasHandler)
                    {
                        localized++;
                        if (data == null || data.Length < 64) throw new InvalidDataException("Missing localization data");
                        using (var memory = new BinaryReader(new MemoryStream(data)))
                        {
                            var bytes = new System.Collections.Generic.List<byte>();
                            byte ch;
                            while ((ch = memory.ReadByte()) != 0) bytes.Add(ch);
                            string typeName = System.Text.Encoding.UTF8.GetString(bytes.ToArray());
                            int magic = memory.ReadInt32();
                            int count = memory.ReadInt32();
                            Console.WriteLine("FSLOC_TYPE " + typeName);
                            Console.WriteLine("FSLOC_MAGIC " + magic.ToString("X8") + " STRINGS=" + count);
                            if (magic != unchecked((int)0xABCD0001) || count < 1 || count > 20000)
                                throw new InvalidDataException("Unexpected localization payload");
                        }
                    }
                    if (resource.Type == ModResourceType.Res && (data == null || data.Length == 0))
                        throw new InvalidDataException("Res payload empty");
                }
                if (localized < 1) throw new InvalidDataException("No localization resource found");
                Console.WriteLine("OFFICIAL_READER_PASS");
                return 0;
            }
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine("VERIFY_FAILURE " + ex.ToString());
            return 1;
        }
    }
}
