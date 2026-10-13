# Rebuild the local Frosty / Flammenwerfer toolchain. No files copied into Git by this script.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Split-Path -Parent $PSScriptRoot
$base = Join-Path $root '.external'
$downloadDir = Join-Path $base 'downloads'
New-Item -ItemType Directory -Force -Path $downloadDir | Out-Null
$packages = @(
    @{Name='FrostyEditor-v1.0.6.3.zip'; Url='https://github.com/CadeEvs/FrostyToolsuite/releases/download/v1.0.6.3/FrostyEditor.zip'; Bytes=95709035; OutDir='frosty\editor-1.0.6.3'},
    @{Name='FrostyModManager-v1.0.6.3.zip'; Url='https://github.com/CadeEvs/FrostyToolsuite/releases/download/v1.0.6.3/FrostyModManager.zip'; Bytes=83316582; OutDir='frosty\modmanager-1.0.6.3'},
    @{Name='FlammenwerferPlugin-v0.4.1-frosty1063.zip'; Url='https://github.com/shoushou1106/FrostyFlammenwerferPlugin/releases/download/v0.4.1/FlammenwerferPlugin_0.4.1_Frosty1.0.6.3orLater.zip'; Bytes=245104; OutDir='frosty\flammenwerfer-0.4.1'}
)
$manifest = @()
foreach ($pkg in $packages) {
    $dest = Join-Path $downloadDir $pkg.Name
    $temp = $dest + '.download'
    $out = Join-Path $base $pkg.OutDir
    if ((Test-Path -LiteralPath $dest) -and ((Get-Item -LiteralPath $dest).Length -ne [long]$pkg.Bytes)) {
        throw "Existing archive has unexpected size: $dest"
    }
    if (-not (Test-Path -LiteralPath $dest)) {
        Write-Output ("DOWNLOADING " + $pkg.Name)
        try {
            Invoke-WebRequest -Uri $pkg.Url -Headers @{'User-Agent'='NFS2015-KoreanPatch-Setup'} -OutFile $temp -MaximumRedirection 8 -TimeoutSec 300 -UseBasicParsing
            if ((Get-Item -LiteralPath $temp).Length -ne [long]$pkg.Bytes) {
                throw ("Downloaded size mismatch for " + $pkg.Name)
            }
            Move-Item -LiteralPath $temp -Destination $dest -ErrorAction Stop
        } finally {
            if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force }
        }
    } else {
        Write-Output ("CACHED " + $pkg.Name)
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($dest)
    try {
        foreach ($entry in $archive.Entries) {
            if ($entry.FullName.StartsWith('/') -or $entry.FullName.Contains('../') -or $entry.FullName.Contains('..\')) {
                throw ('Unsafe ZIP path: ' + $entry.FullName)
            }
        }
    } finally {
        $archive.Dispose()
    }
    if (-not (Test-Path -LiteralPath (Join-Path $out '.nfs-install-complete'))) {
        New-Item -ItemType Directory -Force -Path $out | Out-Null
        Write-Output ("EXTRACTING " + $pkg.Name)
        Expand-Archive -LiteralPath $dest -DestinationPath $out -Force
        New-Item -ItemType File -Path (Join-Path $out '.nfs-install-complete') -Force | Out-Null
    } else {
        Write-Output ("EXTRACTED " + $pkg.Name)
    }
    $sha = (Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash.ToLowerInvariant()
    $manifest += [pscustomobject]@{name=$pkg.Name; url=$pkg.Url; expected_bytes=$pkg.Bytes; sha256=$sha; archive=$dest; extracted=$out}
    Write-Output ("READY " + $pkg.Name + " SHA256=" + $sha)
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $base 'dependency-manifest.json') -Encoding UTF8
Write-Output 'ALL_PACKAGES_DOWNLOADED_EXTRACTED'

$ErrorActionPreference = 'Stop'
$base = Join-Path (Join-Path (Split-Path -Parent $PSScriptRoot) '.external') 'frosty'
$plugin = Join-Path $base 'flammenwerfer-0.4.1\FlammenwerferPlugin.dll'
if (-not (Test-Path -LiteralPath $plugin)) {throw 'Flammenwerfer plugin not found'}
$sets = @(
    @{Name='editor'; Source='editor-1.0.6.3\FrostyEditor'; Target='editor-ko-1.0.6.3\FrostyEditor'; Exe='FrostyEditor.exe'},
    @{Name='manager'; Source='modmanager-1.0.6.3\FrostyModManager'; Target='modmanager-ko-1.0.6.3\FrostyModManager'; Exe='FrostyModManager.exe'}
)
foreach ($s in $sets) {
    $src = Join-Path $base $s.Source
    $dst = Join-Path $base $s.Target
    $exe = Join-Path $dst $s.Exe
    if (-not (Test-Path -LiteralPath $exe)) {
        New-Item -ItemType Directory -Force -Path $dst | Out-Null
        Copy-Item -Path (Join-Path $src '*') -Destination $dst -Recurse -Force -ErrorAction Stop
    }
    $pdir = Join-Path $dst 'Plugins'
    $original = Join-Path $pdir 'FsLocalizationPlugin.dll'
    $disabled = Join-Path $pdir 'FsLocalizationPlugin.dll.disabled'
    if (Test-Path -LiteralPath $original) {
        if (Test-Path -LiteralPath $disabled) { throw "Both vanilla and disabled plugins exist at $pdir" }
        Rename-Item -LiteralPath $original -NewName 'FsLocalizationPlugin.dll.disabled'
    }
    $targetPlugin = Join-Path $pdir 'FlammenwerferPlugin.dll'
    Copy-Item -LiteralPath $plugin -Destination $targetPlugin -Force
    if (-not (Test-Path -LiteralPath $disabled)) { throw "Vanilla localization plugin not disabled at $pdir" }
    if (-not (Test-Path -LiteralPath $targetPlugin)) {throw "Flammenwerfer not installed at $pdir"}
    Write-Output ('KO_TOOL_READY ' + $s.Name + ' ' + $exe)
    Write-Output ('PLUGIN_SHA256 ' + (Get-FileHash -LiteralPath $targetPlugin -Algorithm SHA256).Hash.ToLowerInvariant())
}
Write-Output 'KO_EDITOR_MANAGER_SETUP_COMPLETE'

