param([string]$WorkspaceRoot, [switch]$CheckOnly)
. (Join-Path $PSScriptRoot 'Workspace.Common.ps1')
$root = Resolve-WorkspaceRoot $WorkspaceRoot
$names = @('grill-me', 'grilling', 'playwright-skill', 'ppt-master', 'pptx')
$sourceRoot = Join-Path $root '.claude/skills'
if (-not [IO.Directory]::Exists($sourceRoot)) {
    $sourceRoot = Join-Path $root '.local/skill-source/.claude/skills'
}
$destinationRoot = Join-Path $root '.agents/skills'

# Validate the entire set before creating anything.
foreach ($name in $names) {
    $source = Join-Path $sourceRoot $name
    if (-not [IO.File]::Exists((Join-Path $source 'SKILL.md'))) {
        $source = Join-Path (Join-Path $root '.local/skill-source/.claude/skills') $name
    }
    if (-not [IO.File]::Exists((Join-Path $source 'SKILL.md'))) {
        $source = Join-Path (Join-Path $root '.local/skill-source/.claude/skills') $name
    }
    if (-not [IO.File]::Exists((Join-Path $source 'SKILL.md'))) { throw "Missing source skill: $name" }
    $destination = Join-Path $destinationRoot $name
    if (Test-Path -LiteralPath $destination) {
        $existing = Get-Item -LiteralPath $destination -Force
        if ($existing.LinkType -ne 'Junction' -or [IO.Path]::GetFullPath(@($existing.Target)[0]) -ne [IO.Path]::GetFullPath($source)) {
            throw "Existing registration differs; no overwrite: $name"
        }
    }
}
$registryPath = Get-LocalRegistryPath $root
if ([IO.File]::Exists($registryPath)) {
    $registry = Read-SessionRegistry $root
} else {
    $examplePath = Join-Path $root '작업관리/세션연결/registry.example.json'
    if (-not [IO.File]::Exists($examplePath)) { throw 'Registry example is missing.' }
    $registry = [IO.File]::ReadAllText($examplePath, [Text.Encoding]::UTF8) | ConvertFrom-Json
    Assert-SessionRegistry $registry
    foreach ($entry in $registry.sessions) {
        if ($entry.thread_id -or $entry.verified -or $entry.ack_path) { throw 'Registry example must contain only unregistered, unverified sessions.' }
    }
    if ($registry.codex_binary) { throw 'Registry example must not contain a machine-specific executable.' }
}
$candidates = @()
$command = Get-Command codex.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($command) { $candidates += $command.Source }
if ($env:USERPROFILE) {
    $extensions = Join-Path $env:USERPROFILE '.vscode/extensions'
    if (Test-Path -LiteralPath $extensions) {
        $candidates += @(Get-ChildItem -LiteralPath $extensions -Directory -Filter 'openai.chatgpt-*' |
            Sort-Object LastWriteTime -Descending | ForEach-Object {
                $bin = Join-Path $_.FullName 'bin'
                if (Test-Path -LiteralPath $bin) { Get-ChildItem -LiteralPath $bin -Filter 'codex.exe' -Recurse -File | ForEach-Object { $_.FullName } }
            })
    }
}
$detected = $candidates | Select-Object -First 1
if ($CheckOnly) {
    [pscustomobject]@{ workspace = $root; skills_valid = $true; registry_exists = [IO.File]::Exists($registryPath); codex_detected = [bool]$detected; changed = $false }
    return
}
[IO.Directory]::CreateDirectory($destinationRoot) | Out-Null
foreach ($name in $names) {
    $source = Join-Path $sourceRoot $name
    if (-not [IO.File]::Exists((Join-Path $source 'SKILL.md'))) {
        $source = Join-Path (Join-Path $root '.local/skill-source/.claude/skills') $name
    }
    if (-not [IO.File]::Exists((Join-Path $source 'SKILL.md'))) {
        $source = Join-Path (Join-Path $root '.local/skill-source/.claude/skills') $name
    }
    $destination = Join-Path $destinationRoot $name
    if (-not (Test-Path -LiteralPath $destination)) { New-Item -ItemType Junction -Path $destination -Target $source | Out-Null }
    if ((Get-FileHash -LiteralPath (Join-Path $source 'SKILL.md')).Hash -ne (Get-FileHash -LiteralPath (Join-Path $destination 'SKILL.md')).Hash) { throw "Skill verification failed: $name" }
}
# Existing local registrations, including their CLI selection, are preserved.
if (-not [IO.File]::Exists($registryPath)) {
    if ($detected) { $registry.codex_binary = $detected }
    Save-SessionRegistry $root $registry
}
[pscustomobject]@{ workspace = $root; skills_registered = $names.Count; registry_path = $registryPath; codex_registered = [bool]$registry.codex_binary; sessions_restored = $false }
