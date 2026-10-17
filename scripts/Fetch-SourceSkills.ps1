param([string]$WorkspaceRoot, [string]$ArchiveFile)
. (Join-Path $PSScriptRoot 'Workspace.Common.ps1')
$root = Resolve-WorkspaceRoot $WorkspaceRoot
$lockPath = Join-Path $root 'source-lock.json'
$lock = [IO.File]::ReadAllText($lockPath, [Text.Encoding]::UTF8) | ConvertFrom-Json
if ($lock.repository -ne 'csi20140104-ops/ppt-12' -or $lock.commit -notmatch '^[0-9a-f]{40}$') { throw 'Unexpected source lock.' }
$destination = Join-Path $root '.local/skill-source'
function Assert-Source([string]$Base) {
    foreach ($skill in $lock.skills) {
        if ($skill.name -notmatch '^[a-z0-9-]+$') { throw 'Invalid skill name.' }
        $manifest = Join-Path $Base ('.claude/skills/' + $skill.name + '/SKILL.md')
        if (-not [IO.File]::Exists($manifest) -or (Get-FileHash -LiteralPath $manifest -Algorithm SHA256).Hash.ToLowerInvariant() -ne $skill.sha256) { throw ('Source manifest mismatch: ' + $skill.name) }
    }
}
if (Test-Path -LiteralPath $destination) {
    Assert-Source $destination
    [pscustomobject]@{ source = $destination; commit = $lock.commit; manifests_verified = 5; changed = $false }
    return
}
$cache = Join-Path $root '.local/source-downloads'
[IO.Directory]::CreateDirectory($cache) | Out-Null
if ([string]::IsNullOrWhiteSpace($ArchiveFile)) {
    $ArchiveFile = Join-Path $cache ($lock.commit + '.zip')
    if (-not [IO.File]::Exists($ArchiveFile)) {
        $temporary = $ArchiveFile + '.partial'
        $uri = 'https://codeload.github.com/' + $lock.repository + '/zip/' + $lock.commit
        Invoke-WebRequest -Uri $uri -OutFile $temporary -UseBasicParsing -TimeoutSec 180
        [IO.File]::Move($temporary, $ArchiveFile)
    }
}
$archivePath = [IO.Path]::GetFullPath($ArchiveFile)
if (-not [IO.File]::Exists($archivePath)) { throw 'Source archive is missing.' }
$staging = Join-Path $cache ('extract-' + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($staging) | Out-Null
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::OpenRead($archivePath)
try {
    foreach ($entry in $zip.Entries) {
        $name = $entry.FullName.Replace([char]92, [char]47)
        if ($name -notmatch '^[^/]+/(\.claude/skills/([^/]+)/.*)$') { continue }
        $relative, $skillName = $Matches[1], $Matches[2]
        if ($skillName -notin @($lock.skills | ForEach-Object { $_.name })) { continue }
        if ($relative -match '(^|/)(node_modules|__pycache__|\.venv|venv)(/|$)' -or $relative -match '(^|/)\.env$') { continue }
        $target = [IO.Path]::GetFullPath((Join-Path $staging $relative))
        if (-not $target.StartsWith($staging + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Archive path leaves staging.' }
        if ($name.EndsWith('/')) { [IO.Directory]::CreateDirectory($target) | Out-Null; continue }
        [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target)) | Out-Null
        [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $target, $false)
    }
} finally { $zip.Dispose() }
Assert-Source $staging
[IO.Directory]::Move($staging, $destination)
[pscustomobject]@{ source = $destination; commit = $lock.commit; manifests_verified = 5; changed = $true; dependencies_installed = $false }
