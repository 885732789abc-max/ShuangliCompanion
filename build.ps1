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
& '.venv/Scripts/python.exe' -m PyInstaller --noconfirm --distpath 'build/package-stage' ShuangliBridgeHost.spec
if ($LASTEXITCODE -ne 0) { throw '桥接构建失败' }
New-Item -ItemType Directory -Path 'dist/ShuangliCompanion' -Force | Out-Null
Get-ChildItem -LiteralPath 'build/package-stage/ShuangliCompanion' | Copy-Item -Destination 'dist/ShuangliCompanion' -Recurse -Force
Copy-Item -LiteralPath 'build/package-stage/ShuangliBridgeHost.exe' -Destination 'dist/ShuangliCompanion/ShuangliBridgeHost.exe' -Force
foreach ($part in @('extension','docs')) {
    $target = Join-Path 'dist/ShuangliCompanion' $part
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    Get-ChildItem -LiteralPath $part | Copy-Item -Destination $target -Recurse -Force
}
Copy-Item -LiteralPath 'README.md' -Destination 'dist/ShuangliCompanion/README.md' -Force
Write-Output '构建完成：dist/ShuangliCompanion/ShuangliCompanion.exe'
