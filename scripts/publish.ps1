# Build a self-contained single-file EXIFexit.exe for Windows x64
param([string]$OutputDirectory)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$out = if ($OutputDirectory) { [IO.Path]::GetFullPath($OutputDirectory) } else { Join-Path $root "artifacts\EXIFexit" }

Write-Host "Publishing EXIFexit → $out" -ForegroundColor Cyan

dotnet publish (Join-Path $root "src\EXIFexit.App\EXIFexit.App.csproj") `
  -c Release `
  -r win-x64 `
  --self-contained true `
  -p:PublishSingleFile=true `
  -p:IncludeNativeLibrariesForSelfExtract=true `
  -p:EnableCompressionInSingleFile=true `
  -p:DebugType=none `
  -p:DebugSymbols=false `
  -o $out

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$exe = Join-Path $out "EXIFexit.exe"
if (Test-Path $exe) {
    $len = (Get-Item $exe).Length / 1MB
    Write-Host ("OK: {0} ({1:N1} MB)" -f $exe, $len) -ForegroundColor Green
} else {
    throw "Publish finished but EXE not found."
}
