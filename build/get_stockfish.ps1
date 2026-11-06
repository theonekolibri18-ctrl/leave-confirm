# Lädt Stockfish (Windows) von GitHub und legt die Binaries unter .\stockfish ab.
$ErrorActionPreference = "Stop"
$ver = "sf_17.1"
$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path $root "stockfish"
New-Item -ItemType Directory -Force -Path $out | Out-Null

foreach ($flavor in @("avx2", "sse41-popcnt")) {
    $name = "stockfish-windows-x86-64-$flavor"
    $zip = Join-Path $env:TEMP "$name.zip"
    $dir = Join-Path $env:TEMP "$name"
    Write-Host "Lade $name ..."
    Invoke-WebRequest -Uri "https://github.com/official-stockfish/Stockfish/releases/download/$ver/$name.zip" -OutFile $zip
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    Expand-Archive -Path $zip -DestinationPath $dir -Force
    $exe = Get-ChildItem -Path $dir -Recurse -Filter "*.exe" | Select-Object -First 1
    Copy-Item $exe.FullName (Join-Path $out "$name.exe") -Force
    $lic = Get-ChildItem -Path $dir -Recurse -Filter "Copying.txt" | Select-Object -First 1
    if ($lic) { Copy-Item $lic.FullName (Join-Path $out "Copying.txt") -Force }
}
Set-Content -Path (Join-Path $out "README.txt") -Value @"
Stockfish $ver (GPLv3) - https://github.com/official-stockfish/Stockfish
Quellcode: https://github.com/official-stockfish/Stockfish/tree/$ver
Lizenz: siehe Copying.txt
"@
Write-Host "Stockfish bereit in $out"
