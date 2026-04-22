param(
    [string]$OutputDirectory = "artifacts"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$version = (Get-Content -LiteralPath "VERSION" -Raw).Trim()
if ($version -notmatch '^\d+\.\d+\.\d+$') {
    throw "VERSION must use semantic version format X.Y.Z. Found '$version'."
}

$outputRoot = Join-Path $repoRoot $OutputDirectory
$stagingRoot = Join-Path $outputRoot "staging"
$packageRootName = "AEB-Tools-v$version"
$stagingPackageRoot = Join-Path $stagingRoot $packageRootName
$zipPath = Join-Path $outputRoot "$packageRootName.zip"

if (Test-Path -LiteralPath $stagingRoot) {
    Remove-Item -LiteralPath $stagingRoot -Recurse -Force
}

if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

New-Item -ItemType Directory -Path $stagingPackageRoot -Force | Out-Null

$packageItems = @(
    "AEBTools.extension",
    "README.md",
    "CHANGELOG.md",
    "RELEASE_NOTES.md",
    "VERSION"
)

foreach ($item in $packageItems) {
    Copy-Item -LiteralPath $item -Destination $stagingPackageRoot -Recurse -Force
}

Compress-Archive -Path (Join-Path $stagingPackageRoot "*") -DestinationPath $zipPath -Force

if (Test-Path -LiteralPath $stagingRoot) {
    Remove-Item -LiteralPath $stagingRoot -Recurse -Force
}

Write-Host "Created release package: $zipPath"
