$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$editor = Join-Path $root '.external\frosty\editor-1.0.6.3\FrostyEditor'
$runtime = Join-Path $root 'work\locale-extract\runtime'
New-Item -ItemType Directory -Force -Path $runtime,(Join-Path $runtime 'Profiles'),(Join-Path $runtime 'ThirdParty'),(Join-Path $runtime 'Caches') | Out-Null
foreach ($file in @('FrostySdk.dll','FrostyHash.dll')) {
    Copy-Item -LiteralPath (Join-Path $editor $file) -Destination (Join-Path $runtime $file) -Force
}
Copy-Item -LiteralPath (Join-Path $editor 'Profiles\NFS16SDK.dll') -Destination (Join-Path $runtime 'Profiles\NFS16SDK.dll') -Force
Get-ChildItem -LiteralPath (Join-Path $editor 'ThirdParty') -File | Copy-Item -Destination (Join-Path $runtime 'ThirdParty') -Force
$compiler = "$env:windir\Microsoft.NET\Framework\v4.0.30319\csc.exe"
if (-not (Test-Path -LiteralPath $compiler)) { throw 'NET Framework C# compiler missing' }
$source = Join-Path $PSScriptRoot 'NfsLocaleDump.cs'
$exe = Join-Path $runtime 'NfsLocaleDump.exe'
& $compiler '/nologo' '/target:exe' '/platform:x64' "/out:$exe" "/r:$(Join-Path $runtime 'FrostySdk.dll')" "/r:$(Join-Path $runtime 'FrostyHash.dll')" '/r:Microsoft.CSharp.dll' '/r:System.Core.dll' $source
if ($LASTEXITCODE -ne 0) { throw "Compilation failed with status $LASTEXITCODE" }
Write-Output ("BUILD_OK " + $exe)
Push-Location $runtime
try {
    & $exe '--profile'
    if ($LASTEXITCODE -ne 0) { throw "Profile probe failed with status $LASTEXITCODE" }
} finally { Pop-Location }
Write-Output 'PROFILE_PROBE_OK'
