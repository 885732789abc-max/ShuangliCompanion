param([switch]$Worker)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $Worker) {
    & '.venv/Scripts/python.exe' 'art/guarded_build.py'
    if ($LASTEXITCODE -ne 0) { throw "打包未完成，退出码 $LASTEXITCODE；详情见 build/packaging.log" }
    exit 0
}
& '.venv/Scripts/python.exe' -m PyInstaller --noconfirm --distpath 'build/package-stage' ShuangliCompanion.spec
if ($LASTEXITCODE -ne 0) { throw '桌宠构建失败' }
New-Item -ItemType Directory -Path 'dist/ShuangliCompanion' -Force | Out-Null
Get-ChildItem -LiteralPath 'build/package-stage/ShuangliCompanion' | Copy-Item -Destination 'dist/ShuangliCompanion' -Recurse -Force
# Remove obsolete browser components when overlaying an existing package.
$packageRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'dist/ShuangliCompanion'))
foreach ($obsolete in @('extension', 'ShuangliBridgeHost.exe')) {
    $obsoletePath = [System.IO.Path]::GetFullPath((Join-Path $packageRoot $obsolete))
    if (-not $obsoletePath.StartsWith($packageRoot + [System.IO.Path]::DirectorySeparatorChar)) { throw 'Invalid package cleanup path' }
    if (Test-Path -LiteralPath $obsoletePath) { Remove-Item -LiteralPath $obsoletePath -Recurse -Force }
}
foreach ($part in @('docs')) {
    $target = Join-Path 'dist/ShuangliCompanion' $part
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    Get-ChildItem -LiteralPath $part | Copy-Item -Destination $target -Recurse -Force
}
Copy-Item -LiteralPath 'README.md' -Destination 'dist/ShuangliCompanion/README.md' -Force
Write-Output '构建完成：dist/ShuangliCompanion/ShuangliCompanion.exe'
