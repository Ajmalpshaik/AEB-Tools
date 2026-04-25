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
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "LICENSE",
    "AEBTools.extension",
    "AEBTools.extension\extension.json",
    "AEBTools.extension\AEB Tools.tab\Doors.panel\Room to Door.pushbutton\bundle.yaml",
    "AEBTools.extension\AEB Tools.tab\Doors.panel\Mirror Door.pushbutton\bundle.yaml",
    ".github\CODEOWNERS",
    ".github\PULL_REQUEST_TEMPLATE.md",
    ".github\ISSUE_TEMPLATE\bug_report.yml",
    ".github\ISSUE_TEMPLATE\feature_request.yml",
    ".github\ISSUE_TEMPLATE\config.yml"
)

foreach ($requiredPath in $requiredPaths) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required path not found: $requiredPath"
    }
}

$requiredBundleFiles = @(
    "AEBTools.extension\AEB Tools.tab\Doors.panel\Room to Door.pushbutton\script.py",
    "AEBTools.extension\AEB Tools.tab\Doors.panel\Room to Door.pushbutton\icon.png",
    "AEBTools.extension\AEB Tools.tab\Doors.panel\Mirror Door.pushbutton\script.py",
    "AEBTools.extension\AEB Tools.tab\Doors.panel\Mirror Door.pushbutton\icon.png"
)

foreach ($requiredBundleFile in $requiredBundleFiles) {
    if (-not (Test-Path -LiteralPath $requiredBundleFile)) {
        throw "Required pushbutton asset not found: $requiredBundleFile"
    }
}

$disallowedPaths = @(
    "AEBTools.extension\AEB Tools.tab\Doors.panel\Identify Mirrored Doors.pushbutton",
    "AEBTools.extension\AEB Tools.tab\Doors.panel\Room to Door.pushbutton\README.md",
    "AEBTools.extension\AEB Tools.tab\Doors.panel\Mirror Door.pushbutton\README.md",
    "AEBTools.extension\hooks",
    "AEBTools.extension\startup",
    "AEBTools.extension\tabs",
    "AEBTools.extension\ui_templates",
    "AEBTools.extension\lib\revit_2020",
    "AEBTools.extension\lib\revit_2021",
    "AEBTools.extension\lib\revit_2022",
    "AEBTools.extension\lib\revit_2023",
    "AEBTools.extension\lib\revit_2024",
    "AEBTools.extension\lib\revit_2025",
    "AEBTools.extension\lib\revit_2026",
    "AEBTools.extension\lib\revit_2027"
)

foreach ($disallowedPath in $disallowedPaths) {
    if (Test-Path -LiteralPath $disallowedPath) {
        throw "Disallowed release-path detected: $disallowedPath"
    }
}

$cacheDirectories = Get-ChildItem -Path $repoRoot -Directory -Recurse -Force |
    Where-Object { $_.Name -eq "__pycache__" }
if ($cacheDirectories) {
    $cacheDirectories | ForEach-Object { Write-Host $_.FullName }
    throw "Python cache directories detected in public repository."
}

$compiledPythonFiles = Get-ChildItem -Path $repoRoot -File -Recurse -Force |
    Where-Object { $_.Extension -in @(".pyc", ".pyo") }
if ($compiledPythonFiles) {
    $compiledPythonFiles | ForEach-Object { Write-Host $_.FullName }
    throw "Compiled Python artifacts detected in public repository."
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
