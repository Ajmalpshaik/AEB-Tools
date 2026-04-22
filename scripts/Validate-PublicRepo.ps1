Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

function Read-TrimmedFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Required file not found: $Path"
    }

    return (Get-Content -LiteralPath $Path -Raw).Trim()
}

$version = Read-TrimmedFile -Path "VERSION"

if ($version -notmatch '^\d+\.\d+\.\d+$') {
    throw "VERSION must use semantic version format X.Y.Z. Found '$version'."
}

$requiredPaths = @(
    "README.md",
    "CHANGELOG.md",
    "RELEASE_NOTES.md",
    "AEBTools.extension",
    "AEBTools.extension\extension.json",
    "AEBTools.extension\AEB Tools.tab\Doors.panel\Room to Door.pushbutton\bundle.yaml"
)

foreach ($requiredPath in $requiredPaths) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required path not found: $requiredPath"
    }
}

$bundleText = Get-Content -LiteralPath "AEBTools.extension\AEB Tools.tab\Doors.panel\Room to Door.pushbutton\bundle.yaml" -Raw
if ($bundleText -notmatch "(?m)^# Version\s+:\s+$([regex]::Escape($version))`r?$") {
    throw "bundle.yaml header version does not match VERSION ($version)."
}

$releaseNotes = Get-Content -LiteralPath "RELEASE_NOTES.md" -Raw
if ($releaseNotes -notmatch "(?m)^## $([regex]::Escape($version)) - \d{4}-\d{2}-\d{2}`r?$") {
    throw "RELEASE_NOTES.md must contain a heading for version $version."
}

$changelog = Get-Content -LiteralPath "CHANGELOG.md" -Raw
if ($changelog -notmatch "(?m)^## \[$([regex]::Escape($version))\] - \d{4}-\d{2}-\d{2}`r?$") {
    throw "CHANGELOG.md must contain an entry for version $version."
}

$extension = Get-Content -LiteralPath "AEBTools.extension\extension.json" -Raw | ConvertFrom-Json
if ($extension.url -ne "https://github.com/Ajmalpshaik/AEB-Tools") {
    throw "extension.json url must point to the public repository."
}

$githubRefName = $env:GITHUB_REF_NAME
if ($githubRefName -and $githubRefName.StartsWith("v")) {
    $expectedTag = "v$version"
    if ($githubRefName -ne $expectedTag) {
        throw "Git tag '$githubRefName' does not match VERSION '$version'. Expected '$expectedTag'."
    }
}

Write-Host "Public repository validation passed for version $version."
