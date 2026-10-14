# Create a portable Windows x64 ZIP, including data, licenses, and SHA-256.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
[xml]$project = Get-Content (Join-Path $root "src\EXIFexit.App\EXIFexit.App.csproj")
$version = [string]$project.Project.PropertyGroup.Version
if (-not $version) { throw "Application version is missing." }
$name = "EXIFexit-$version-win-x64-portable"
$buildRoot = Join-Path $root ("artifacts\portable-" + [guid]::NewGuid().ToString("N"))
$bundle = Join-Path $buildRoot $name
$releaseDir = Join-Path $root "artifacts\releases"
New-Item -ItemType Directory -Path $bundle, $releaseDir -Force | Out-Null

& (Join-Path $PSScriptRoot "publish.ps1") -OutputDirectory $bundle
if ($LASTEXITCODE -ne 0) { throw "Publish failed." }
Copy-Item -LiteralPath (Join-Path $root "LICENSE") -Destination $bundle
Copy-Item -LiteralPath (Join-Path $root "docs\PUBLICATION_AUDIT.md") -Destination $bundle
@'
EXIF EXIT - PORTABLE WINDOWS APPLICATION

1. Extract the entire ZIP into a folder you can write to.
2. Open EXIFexit.exe.

No installer, Python, administrator privileges, or separate .NET runtime required.
For Windows x64. Keep the data and licenses folders with the executable.
Start with copies of your files. Outputs are copies by default.

This build is unsigned. It includes the .NET runtime and third-party libraries.
Known dependency advisories remain; see PUBLICATION_AUDIT.md. PDF rewriting is
not full sanitization/redaction and can invalidate signatures or discard features.
Metadata verification checks selected fields, not every possible data channel.

Source, full documentation, and updates:
https://github.com/RawPowered/EXIFexit

The SHA256SUMS.txt release asset lets you verify the downloaded ZIP:
  Get-FileHash .\EXIFexit-2.0.0-win-x64-portable.zip -Algorithm SHA256
'@ | Set-Content -LiteralPath (Join-Path $bundle "START-HERE.txt") -Encoding utf8

# Preserve package license files and license metadata with the distributed build.
$assets = Get-Content (Join-Path $root "src\EXIFexit.App\obj\project.assets.json") -Raw | ConvertFrom-Json
$licenseDir = Join-Path $bundle "licenses"
New-Item -ItemType Directory -Path $licenseDir | Out-Null
$notices = [Collections.Generic.List[string]]::new()
$notices.Add("Third-party packages: license metadata and included license files")
foreach ($entry in $assets.libraries.PSObject.Properties) {
    if ($entry.Value.type -ne "package") { continue }
    $packageDir = $null
    foreach ($folder in $assets.packageFolders.PSObject.Properties.Name) {
        $candidate = Join-Path $folder $entry.Value.path
        if (Test-Path -LiteralPath $candidate) { $packageDir = $candidate; break }
    }
    if (-not $packageDir) { throw "Package not found: $($entry.Name)" }
    $destination = Join-Path $licenseDir ($entry.Name.Replace('/', '-'))
    New-Item -ItemType Directory -Path $destination | Out-Null
    $nuspec = Get-ChildItem -LiteralPath $packageDir -Filter *.nuspec | Select-Object -First 1
    if (-not $nuspec) { throw "Package metadata not found: $($entry.Name)" }
    [xml]$metadata = Get-Content -LiteralPath $nuspec.FullName
    $notices.Add("")
    $notices.Add($entry.Name)
    foreach ($node in $metadata.SelectNodes("//*[local-name()='metadata']/*[local-name()='authors' or local-name()='copyright' or local-name()='license' or local-name()='licenseUrl' or local-name()='projectUrl' or local-name()='repository']")) {
        $notices.Add($node.OuterXml)
    }
    Get-ChildItem -LiteralPath $packageDir -File -Recurse | Where-Object {
        $_.Name -match '(?i)(license|licence|copyright|notice)' -and $_.Extension -notin '.dll', '.pdb', '.xml'
    } | ForEach-Object {
        $relative = $_.FullName.Substring($packageDir.Length).TrimStart('\', '/')
        $target = Join-Path $destination $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $target
    }
}
# Self-contained runtime packs are not listed as normal library entries.
foreach ($download in $assets.project.frameworks.PSObject.Properties.Value.downloadDependencies) {
    if ($download.name -notmatch '^Microsoft\.(NETCore|WindowsDesktop)\.App\.Runtime\.win-x64$') { continue }
    $runtimeVersion = ($download.version.Trim('[', ']') -split ',')[0].Trim()
    $runtimeFound = $false
    foreach ($folder in $assets.packageFolders.PSObject.Properties.Name) {
        $runtimeDir = Join-Path $folder ($download.name.ToLowerInvariant() + '/' + $runtimeVersion)
        if (-not (Test-Path -LiteralPath $runtimeDir)) { continue }
        $targetDir = Join-Path $licenseDir ($download.name + '-' + $runtimeVersion)
        New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
        Get-ChildItem -LiteralPath $runtimeDir -File | Where-Object { $_.Name -match '(?i)(license|notice)' } | Copy-Item -Destination $targetDir
        $notices.Add("`nBundled runtime: $($download.name)/$runtimeVersion")
        $runtimeFound = $true
        break
    }
    if (-not $runtimeFound) { throw "Runtime license files not found: $($download.name)/$runtimeVersion" }
}
$notices | Set-Content -LiteralPath (Join-Path $bundle "THIRD-PARTY-NOTICES.txt") -Encoding utf8
$zip = Join-Path $releaseDir "$name.zip"
Compress-Archive -LiteralPath $bundle -DestinationPath $zip -Force
$hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  $name.zip" | Set-Content -LiteralPath (Join-Path $releaseDir "SHA256SUMS.txt") -Encoding ascii
Write-Host "Portable ZIP: $zip"
Write-Host "SHA-256: $hash"
