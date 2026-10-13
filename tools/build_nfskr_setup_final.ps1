$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$py=Join-Path $root '.external\nfskr-build-venv\Scripts\python.exe'
$payload=Join-Path $root 'work\installer-build\bundle_assets'
$icon=Join-Path $root 'work\installer-build\nfskr.ico'
$logo=Join-Path $root 'work\installer-build\nfskr-logo.png'
$github=Join-Path $root 'work\installer-build\github-mark.png'
$dist=Join-Path $root 'work\installer-build\release-candidate'
$dest=Join-Path $dist 'NFSKR-Setup.exe'
if (!(Test-Path -LiteralPath $py)) {throw 'Build environment not found'}
& $py (Join-Path $root 'tools\make_nfskr_icon.py')
if ($LASTEXITCODE -ne 0) {throw 'Approved NFSKR logo build failed'}
if (!(Test-Path -LiteralPath $icon)) {throw 'NFSKR icon not generated'}
if (!(Test-Path -LiteralPath $logo)) {throw 'Approved NFSKR logo PNG not generated'}
if (!(Test-Path -LiteralPath $github)) {throw 'GitHub mark asset not found'}
if (!(Test-Path -LiteralPath (Join-Path $payload 'translation\nfskr-first-release-v1.1.json'))) {throw 'Missing frozen Korean translation'}
if (Test-Path -LiteralPath $dest) {throw 'Release candidate already exists; refusing silent overwrite'}
$arguments=@(
 '-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed',
 '--name','NFSKR-Setup',
 '--icon',$icon,
 '--add-data',("$payload;bundle_assets"),
 '--add-data',("$icon;."),
 '--add-data',("$logo;."),
 '--add-data',("$github;."),
 '--collect-all','customtkinter',
 '--hidden-import','nfskr_modern_ui',
 '--hidden-import','nfskr_credits',
 '--hidden-import','nfskr_discovery',
 '--hidden-import','nfskr_bootstrap',
 '--hidden-import','nfskr_fonts',
 '--hidden-import','nfskr_shortcuts',
 '--hidden-import','nfskr_progress',
 '--hidden-import','nfskr_setup_flow',
 '--hidden-import','nfskr_local_assets',
 '--hidden-import','nfskr_composite',
 '--hidden-import','verify_nfskr_composite',
 '--hidden-import','nfskr_installer_core',
 '--hidden-import','nfskr_fbmod_format',
 '--hidden-import','nfskr_locale_codec',
 '--hidden-import','mod_merge_core',
 '--hidden-import','lz4.block',
 '--collect-submodules','fontTools',
 '--distpath',$dist,
 '--workpath',(Join-Path $root 'work\installer-build\final-work'),
 '--specpath',(Join-Path $root 'work\installer-build\final-spec'),
 (Join-Path $root 'tools\nfskr_setup_gui.py')
)
& $py @arguments
if ($LASTEXITCODE -ne 0) {throw 'Windows EXE final build failed'}
if (!(Test-Path -LiteralPath $dest)) {throw 'NFSKR-Setup.exe was not generated'}
Get-Item -LiteralPath $dest | Select-Object FullName,Length
Get-FileHash -Algorithm SHA256 -LiteralPath $dest | Select-Object Hash
Write-Output 'NFSKR_WINDOWS_EXE_FINAL_BUILT'
