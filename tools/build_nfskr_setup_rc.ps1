$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$py=Join-Path $root '.external\nfskr-build-venv\Scripts\python.exe'
$payload=Join-Path $root 'work\installer-build\bundle_assets'
if(!(Test-Path -LiteralPath (Join-Path $payload 'translation\nfskr-first-release-v1.1.json'))){throw 'Release payload absent'}
& $py -m PyInstaller --noconfirm --clean --onefile --windowed --name NFSKR-Setup-RC `
  --add-data "$payload;bundle_assets" `
  --hidden-import nfskr_setup_flow `
  --hidden-import nfskr_local_assets `
  --hidden-import nfskr_composite `
  --hidden-import verify_nfskr_composite `
  --hidden-import nfskr_installer_core `
  --hidden-import nfskr_fbmod_format `
  --hidden-import nfskr_locale_codec `
  --hidden-import mod_merge_core `
  --hidden-import lz4.block `
  --collect-submodules fontTools `
  --distpath (Join-Path $root 'work\installer-build\rc-dist') `
  --workpath (Join-Path $root 'work\installer-build\rc-work') `
  --specpath (Join-Path $root 'work\installer-build\rc-spec') `
  (Join-Path $root 'tools\nfskr_setup_gui.py')
if($LASTEXITCODE -ne 0){throw 'PyInstaller release-candidate build failed'}
$exe=Join-Path $root 'work\installer-build\rc-dist\NFSKR-Setup-RC.exe'
if(!(Test-Path -LiteralPath $exe)){throw 'Release-candidate executable missing'}
Get-Item -LiteralPath $exe | Select-Object FullName,Length
Get-FileHash -Algorithm SHA256 -LiteralPath $exe | Select-Object Hash
