$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Write-Ok([string]$m) { Write-Host "[OK] $m" -ForegroundColor Green }
function Write-WarnPl([string]$m) { Write-Host "[UWAGA] $m" -ForegroundColor Yellow }

function Get-VersionKey([string]$version) {
    return (($version -split '\.') | ForEach-Object { '{0:D10}' -f [int]$_ }) -join '.'
}

function Get-BumpedVersion([string]$version) {
    $parts = @($version -split '\.')
    if ($parts.Count -lt 1) { throw "Nieprawidłowa wersja: $version" }
    $parts[$parts.Count - 1] = ([int]$parts[$parts.Count - 1] + 1).ToString()
    return ($parts -join '.')
}

function Write-Utf8NoBom([string]$path, [string]$text) {
    $enc = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($path, $text, $enc)
}

function Write-Md5File([string]$filePath, [string]$md5Path) {
    $hash = (Get-FileHash -LiteralPath $filePath -Algorithm MD5).Hash.ToLowerInvariant()
    Write-Utf8NoBom $md5Path $hash
}

function Get-LatestZip([string]$folder) {
    $items = @()
    Get-ChildItem -LiteralPath $folder -File -Filter '*.zip' | ForEach-Object {
        $m = [regex]::Match($_.BaseName, '^(?<id>.+)-(?<ver>\d+(?:\.\d+)+)$')
        if ($m.Success) {
            $items += [pscustomobject]@{
                File    = $_
                AddonId = $m.Groups['id'].Value
                Version = $m.Groups['ver'].Value
                SortKey = Get-VersionKey $m.Groups['ver'].Value
            }
        }
    }
    if ($items.Count -eq 0) { return $null }
    return ($items | Sort-Object SortKey, @{ Expression = { $_.File.Name } } | Select-Object -Last 1)
}

function New-ZipFromDirectory([string]$sourceDir, [string]$zipPath) {
    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }

    $zip = [System.IO.Compression.ZipFile]::Open($zipPath, [System.IO.Compression.ZipArchiveMode]::Create)
    try {
        $baseFull = [System.IO.Path]::GetFullPath($sourceDir)
        if (-not $baseFull.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
            $baseFull += [System.IO.Path]::DirectorySeparatorChar
        }
        $baseUri = [Uri]$baseFull
        $items = Get-ChildItem -LiteralPath $sourceDir -Recurse -Force | Sort-Object FullName

        foreach ($item in $items) {
            $itemFull = [System.IO.Path]::GetFullPath($item.FullName)
            $rel = $baseUri.MakeRelativeUri([Uri]$itemFull).ToString().Replace('%20', ' ')
            if ([string]::IsNullOrWhiteSpace($rel)) { continue }
            $rel = $rel -replace '\\', '/'

            if ($item.PSIsContainer) {
                $hasChildren = Get-ChildItem -LiteralPath $item.FullName -Force | Select-Object -First 1
                if (-not $hasChildren) {
                    $null = $zip.CreateEntry(($rel.TrimEnd('/') + '/'))
                }
            }
            else {
                [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                    $zip,
                    $item.FullName,
                    $rel,
                    [System.IO.Compression.CompressionLevel]::Optimal
                ) | Out-Null
            }
        }
    }
    finally {
        $zip.Dispose()
    }
}

$RepoRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
Set-Location $RepoRoot
$ZipsRoot = Join-Path $RepoRoot 'Zips'
if (-not (Test-Path -LiteralPath $ZipsRoot -PathType Container)) {
    throw "Brak katalogu 'Zips' obok pliku BAT/PS1."
}

$addonFolders = @(Get-ChildItem -LiteralPath $ZipsRoot -Directory | Sort-Object Name)
if ($addonFolders.Count -eq 0) {
    throw "W katalogu Zips nie ma folderów dodatków."
}

$processed = New-Object System.Collections.Generic.List[object]

foreach ($addonFolder in $addonFolders) {
    $latest = Get-LatestZip $addonFolder.FullName
    if ($null -eq $latest) {
        Write-WarnPl "Pomijam $($addonFolder.Name) - brak paczek ZIP dodatku."
        continue
    }

    $stageRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("repo_bump_" + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null

    try {
        [System.IO.Compression.ZipFile]::ExtractToDirectory($latest.File.FullName, $stageRoot)

        $topDirs = @(Get-ChildItem -LiteralPath $stageRoot -Directory | Sort-Object Name)
        if ($topDirs.Count -ne 1) {
            throw "ZIP '$($latest.File.Name)' ma nieoczekiwaną strukturę. Wymagany jest 1 katalog główny."
        }

        $packRoot = $topDirs[0].FullName
        $addonXmlPath = Join-Path $packRoot 'addon.xml'
        if (-not (Test-Path -LiteralPath $addonXmlPath -PathType Leaf)) {
            throw "Brak addon.xml w ZIP: $($latest.File.Name)"
        }

        $raw = Get-Content -LiteralPath $addonXmlPath -Raw
        $mVersion = [regex]::Match($raw, '(?is)<addon\b[^>]*\bversion="([^"]+)"')
        if (-not $mVersion.Success) {
            throw "Nie udało się odczytać wersji z: $addonXmlPath"
        }

        $currentVersion = $mVersion.Groups[1].Value
        $newVersion = Get-BumpedVersion $currentVersion
        $newRaw = $raw.Substring(0, $mVersion.Groups[1].Index) + $newVersion + $raw.Substring($mVersion.Groups[1].Index + $mVersion.Groups[1].Length)

        $mId = [regex]::Match($newRaw, '(?is)<addon\b[^>]*\bid="([^"]+)"')
        if ($mId.Success) {
            $addonId = $mId.Groups[1].Value
        }
        else {
            $addonId = $topDirs[0].Name
        }

        Write-Utf8NoBom $addonXmlPath $newRaw

        $newZipPath = Join-Path $addonFolder.FullName ($addonId + '-' + $newVersion + '.zip')
        New-ZipFromDirectory $stageRoot $newZipPath
        Write-Md5File $newZipPath ($newZipPath + '.md5')

        $processed.Add([pscustomobject]@{
            AddonId = $addonId
            ZipPath  = $newZipPath
            Version  = $newVersion
        }) | Out-Null

        Write-Ok ("{0}: {1} -> {2}" -f $addonId, $currentVersion, $newVersion)
    }
    finally {
        if (Test-Path -LiteralPath $stageRoot) {
            Remove-Item -LiteralPath $stageRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

if ($processed.Count -eq 0) {
    throw "Nie udało się przetworzyć żadnego dodatku."
}

$addonsXmlParts = New-Object System.Collections.Generic.List[string]
$addonsXmlParts.Add('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
$addonsXmlParts.Add('<addons>')

foreach ($item in ($processed | Sort-Object AddonId)) {
    $stageRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("repo_addonsxml_" + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null

    try {
        [System.IO.Compression.ZipFile]::ExtractToDirectory($item.ZipPath, $stageRoot)
        $topDirs = @(Get-ChildItem -LiteralPath $stageRoot -Directory | Sort-Object Name)
        if ($topDirs.Count -ne 1) {
            throw "Nowy ZIP '$([System.IO.Path]::GetFileName($item.ZipPath))' ma nieoczekiwaną strukturę."
        }

        $addonXmlPath = Join-Path $topDirs[0].FullName 'addon.xml'
        if (-not (Test-Path -LiteralPath $addonXmlPath -PathType Leaf)) {
            throw "Brak addon.xml w nowej paczce ZIP: $($item.ZipPath)"
        }

        $raw = Get-Content -LiteralPath $addonXmlPath -Raw
        $raw = $raw -replace '^\uFEFF', ''
        $raw = [regex]::Replace($raw, '^\s*<\?xml[^>]*\?>\s*', '', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
        $addonsXmlParts.Add($raw.Trim())
    }
    finally {
        if (Test-Path -LiteralPath $stageRoot) {
            Remove-Item -LiteralPath $stageRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

$addonsXmlParts.Add('</addons>')
$addonsXmlPath = Join-Path $RepoRoot 'addons.xml'
Write-Utf8NoBom $addonsXmlPath (($addonsXmlParts -join [Environment]::NewLine) + [Environment]::NewLine)
Write-Md5File $addonsXmlPath (Join-Path $RepoRoot 'addons.xml.md5')

Write-Host ''
Write-Ok 'Gotowe. Zaktualizowano ZIP-y, pliki .md5, addons.xml i addons.xml.md5.'
