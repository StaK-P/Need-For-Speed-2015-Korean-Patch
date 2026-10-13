# Downloads only original OFL-licensed fonts from version-pinned upstream GitHub commits.
# Assets and licenses are stored under .external/, never added to this project Git repository.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$project = Split-Path -Parent $PSScriptRoot
$target = Join-Path $project '.external\fonts\vendor'
New-Item -ItemType Directory -Force -Path $target | Out-Null

$revisions = @{
    'SUITE' = 'a114fec078bfcbdc93a7b2190510ab83de2a2d40'
    'SUIT' = '55118d981336d8fce005eb62888c12c0568ef7b0'
    'pretendard' = '7aeb0698819be2b4097dae8ec8fe6a795e5cf3ae'
}
$files = @(
    @{Project='SUITE'; Org='sun-typeface'; File='fonts/static/ttf/SUITE-ExtraBold.ttf'; Length=566812},
    @{Project='SUITE'; Org='sun-typeface'; File='fonts/static/ttf/SUITE-Heavy.ttf'; Length=566472},
    @{Project='SUIT'; Org='sun-typeface'; File='fonts/static/ttf/SUIT-Regular.ttf'; Length=594324},
    @{Project='SUIT'; Org='sun-typeface'; File='fonts/static/ttf/SUIT-Medium.ttf'; Length=592832},
    @{Project='pretendard'; Org='orioncactus'; File='packages/pretendard/dist/public/variable/PretendardVariable.ttf'; Length=6739336},
    @{Project='SUITE'; Org='sun-typeface'; File='LICENSE'; Length=4382},
    @{Project='SUIT'; Org='sun-typeface'; File='LICENSE'; Length=4380},
    @{Project='pretendard'; Org='orioncactus'; File='LICENSE'; Length=4816}
)
$manifest = @()
foreach ($item in $files) {
    $relative = $item.File
    $filename = Split-Path -Leaf $relative
    if ($filename -eq 'LICENSE') { $filename = $item.Project + '-OFL-LICENSE.txt' }
    $destination = Join-Path $target $filename
    $revision = $revisions[$item.Project]
    $url = "https://raw.githubusercontent.com/$($item.Org)/$($item.Project)/$revision/$relative"
    if (!(Test-Path -LiteralPath $destination)) {
        Write-Output ("DOWNLOAD " + $filename)
        $tmp = $destination + '.partial'
        try {
            Invoke-WebRequest -Uri $url -OutFile $tmp -TimeoutSec 120 -Headers @{'User-Agent'='NFS2015-KoreanPatch-Fonts'}
            if ((Get-Item -LiteralPath $tmp).Length -ne [long]$item.Length) {
                throw "Unexpected size for $filename"
            }
            Move-Item -LiteralPath $tmp -Destination $destination
        } finally {
            if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force }
        }
    }
    if ((Get-Item -LiteralPath $destination).Length -ne [long]$item.Length) { throw "Size mismatch for $filename" }
    $sha = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
    $manifest += [pscustomobject]@{name=$filename; repository="$($item.Org)/$($item.Project)"; revision=$revision; upstream=$url; sha256=$sha; size=$item.Length}
    Write-Output ("READY " + $filename + " SHA256=" + $sha)
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $target 'download-manifest.json') -Encoding UTF8
Write-Output ('FONT_DOWNLOAD_COMPLETE ' + $manifest.Count + ' original files')
