[CmdletBinding()]
param(
    [switch]$SkipPyInstaller
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$ReleaseRoot = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot "release"))
$DistRoot = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot "dist\TLC-RAPID"))

function Assert-ChildPath([string]$Path, [string]$Parent) {
    $full = [System.IO.Path]::GetFullPath($Path)
    $parentFull = [System.IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
    if (-not $full.StartsWith($parentFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe release path outside expected directory: $full"
    }
}

function Reset-ReleaseDirectory([string]$Path) {
    Assert-ChildPath $Path $ReleaseRoot
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Path | Out-Null
}

function Write-Manifest([string]$Root, [string]$OutputName) {
    $output = Join-Path $Root $OutputName
    $lines = Get-ChildItem -LiteralPath $Root -File -Recurse |
        Where-Object { $_.FullName -ne $output } |
        Sort-Object FullName |
        ForEach-Object {
            $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
            $relative = $_.FullName.Substring($Root.Length).TrimStart('\').Replace('\', '/')
            "$hash  $relative"
        }
    [System.IO.File]::WriteAllLines($output, $lines, [System.Text.UTF8Encoding]::new($false))
}

Set-Location $ProjectRoot

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is required to create a traceable release."
}

$dirty = git status --porcelain
if ($LASTEXITCODE -ne 0) { throw "Unable to read Git status." }
if ($dirty) {
    throw "Release build refused: commit all source changes first so the executable has matching source."
}

$ReleaseTag = (git describe --tags --exact-match 2>$null)
if ($LASTEXITCODE -ne 0 -or -not $ReleaseTag) {
    throw "Release build refused: HEAD must have an exact version tag such as v1.0.0."
}
$ReleaseCommit = (git rev-parse HEAD).Trim()
$AppVersion = $ReleaseTag.TrimStart('v')

$DeclaredVersion = python -c "from app_metadata import APP_VERSION; print(APP_VERSION)"
if ($LASTEXITCODE -ne 0 -or $DeclaredVersion.Trim() -ne $AppVersion) {
    throw "Tag $ReleaseTag does not match app_metadata.APP_VERSION ($DeclaredVersion)."
}

$ExpectedWeightHash = "E507240E8C7BB8E8C3C57ABB20ADEE6FEBA78670F2EDF6E06BCF1AE12A4440A5"
$WeightPath = Join-Path $ProjectRoot "weights\best.pt"
if (-not (Test-Path -LiteralPath $WeightPath -PathType Leaf)) {
    throw "Missing release model: $WeightPath"
}
$ActualWeightHash = (Get-FileHash -LiteralPath $WeightPath -Algorithm SHA256).Hash
if ($ActualWeightHash -ne $ExpectedWeightHash) {
    throw "weights/best.pt does not match the documented v1.0.0 SHA-256."
}

python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Unit tests failed." }
python collect_third_party_licenses.py
if ($LASTEXITCODE -ne 0) { throw "Third-party license collection failed." }
$licenseChanges = git status --porcelain -- THIRD_PARTY_LICENSES requirements-freeze.txt
if ($LASTEXITCODE -ne 0 -or $licenseChanges) {
    throw "Collected license files differ from the committed release materials. Commit the updated files first."
}

if (-not $SkipPyInstaller) {
    python -m PyInstaller --noconfirm TLC-RAPID.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }
}
if (-not (Test-Path -LiteralPath (Join-Path $DistRoot "TLC-RAPID.exe") -PathType Leaf)) {
    throw "Frozen executable not found at $DistRoot\TLC-RAPID.exe"
}

New-Item -ItemType Directory -Path $ReleaseRoot -Force | Out-Null
$StagingRoot = Join-Path $ReleaseRoot "staging-$ReleaseTag"
$SourceStage = Join-Path $StagingRoot "TLC-RAPID-$ReleaseTag-source"
$WindowsStage = Join-Path $StagingRoot "TLC-RAPID-$ReleaseTag-windows-x64"
Reset-ReleaseDirectory $StagingRoot
New-Item -ItemType Directory -Path $SourceStage, $WindowsStage | Out-Null

$GitArchive = Join-Path $StagingRoot "tracked-source.zip"
git archive --format=zip --output=$GitArchive HEAD
if ($LASTEXITCODE -ne 0) { throw "git archive failed." }
Expand-Archive -LiteralPath $GitArchive -DestinationPath $SourceStage
Remove-Item -LiteralPath $GitArchive -Force

New-Item -ItemType Directory -Path (Join-Path $SourceStage "weights") -Force | Out-Null
Copy-Item -LiteralPath $WeightPath -Destination (Join-Path $SourceStage "weights\best.pt")

Copy-Item -Path (Join-Path $DistRoot "*") -Destination $WindowsStage -Recurse -Force
Copy-Item -LiteralPath (Join-Path $ProjectRoot "user_input") -Destination $WindowsStage -Recurse
$WindowsImages = Join-Path $WindowsStage "user_input\images"
Assert-ChildPath $WindowsImages $WindowsStage
if (Test-Path -LiteralPath $WindowsImages) {
    Remove-Item -LiteralPath $WindowsImages -Recurse -Force
}
New-Item -ItemType Directory -Path $WindowsImages | Out-Null
Copy-Item -LiteralPath (Join-Path $ProjectRoot "user_input\images\PLACE_IMAGES_HERE.txt") -Destination $WindowsImages
New-Item -ItemType Directory -Path (Join-Path $WindowsStage "weights") -Force | Out-Null
Copy-Item -LiteralPath $WeightPath -Destination (Join-Path $WindowsStage "weights\best.pt")
Copy-Item -LiteralPath (Join-Path $ProjectRoot "weights\boCenColor.yaml") -Destination (Join-Path $WindowsStage "weights\boCenColor.yaml")
New-Item -ItemType Directory -Path (Join-Path $WindowsStage "runs\predict-seg") -Force | Out-Null

$ReleaseDocs = @(
    "README.md", "README_zh.md", "LICENSE", "LICENSING.md", "COPYRIGHT.txt",
    "MODIFICATIONS.md", "THIRD_PARTY_NOTICES.txt", "CITATION.cff",
    "MODEL_CARD.md", "MODEL_WEIGHTS.md", "DATA.md", "REPRODUCIBILITY.md",
    "CHANGELOG.md", "RELEASE_CHECKLIST.md", "requirements-lock.txt",
    "requirements-freeze.txt"
)
foreach ($doc in $ReleaseDocs) {
    Copy-Item -LiteralPath (Join-Path $ProjectRoot $doc) -Destination (Join-Path $WindowsStage $doc)
}
Copy-Item -LiteralPath (Join-Path $ProjectRoot "THIRD_PARTY_LICENSES") -Destination $WindowsStage -Recurse
Copy-Item -LiteralPath (Join-Path $ProjectRoot "requirements-freeze.txt") -Destination (Join-Path $WindowsStage "PACKAGE_VERSIONS.txt")

$SourceUrl = "https://github.com/zongxuli709-code/TLC-RAPID"
$sourceNotice = @"
TLC-RAPID $ReleaseTag

This package was built from commit:
$ReleaseCommit

The complete corresponding source archive distributed alongside this package is:
TLC-RAPID-$ReleaseTag-source.zip

Release page:
$SourceUrl/releases/tag/$ReleaseTag

Repository:
$SourceUrl

License: GNU AGPL-3.0-only. See LICENSE and LICENSING.md.
"@
foreach ($stage in @($SourceStage, $WindowsStage)) {
    [System.IO.File]::WriteAllText((Join-Path $stage "SOURCE_CODE.txt"), $sourceNotice, [System.Text.UTF8Encoding]::new($false))
    [System.IO.File]::WriteAllText((Join-Path $stage "VERSION.txt"), "$ReleaseTag`n$ReleaseCommit`n", [System.Text.UTF8Encoding]::new($false))
    Write-Manifest $stage "SHA256SUMS.txt"
}

$SourceZip = Join-Path $ReleaseRoot "TLC-RAPID-$ReleaseTag-source.zip"
$WindowsZip = Join-Path $ReleaseRoot "TLC-RAPID-$ReleaseTag-windows-x64.zip"
foreach ($zip in @($SourceZip, $WindowsZip)) {
    Assert-ChildPath $zip $ReleaseRoot
    if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
}
Compress-Archive -LiteralPath $SourceStage -DestinationPath $SourceZip -CompressionLevel Optimal
Compress-Archive -LiteralPath $WindowsStage -DestinationPath $WindowsZip -CompressionLevel Optimal

$topManifest = @()
$topManifest += "{0}  {1}" -f (
    Get-FileHash -LiteralPath $SourceZip -Algorithm SHA256
).Hash, (Split-Path $SourceZip -Leaf)
$topManifest += "{0}  {1}" -f (
    Get-FileHash -LiteralPath $WindowsZip -Algorithm SHA256
).Hash, (Split-Path $WindowsZip -Leaf)
[System.IO.File]::WriteAllLines((Join-Path $ReleaseRoot "SHA256SUMS.txt"), $topManifest, [System.Text.UTF8Encoding]::new($false))

Remove-Item -LiteralPath $StagingRoot -Recurse -Force

Write-Host ""
Write-Host "Release complete:"
Write-Host "  $SourceZip"
Write-Host "  $WindowsZip"
Write-Host "  $(Join-Path $ReleaseRoot 'SHA256SUMS.txt')"
