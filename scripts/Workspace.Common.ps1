$ErrorActionPreference = 'Stop'

function Resolve-WorkspaceRoot([string]$Root) {
    if ([string]::IsNullOrWhiteSpace($Root)) { $Root = Split-Path -Parent $PSScriptRoot }
    $resolved = [IO.Path]::GetFullPath($Root)
    if (-not [IO.Directory]::Exists($resolved)) { throw 'Workspace root does not exist.' }
    return $resolved
}

function Get-LocalRegistryPath([string]$Root) {
    return Join-Path $Root '.local/session-registry.json'
}

function Read-SessionRegistry([string]$Root) {
    $path = Get-LocalRegistryPath $Root
    if (-not [IO.File]::Exists($path)) { throw 'Local registry is missing. Run Initialize-Workspace.ps1 first.' }
    $registry = [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8) | ConvertFrom-Json
    Assert-SessionRegistry $registry
    return $registry
}

function Assert-SessionRegistry($Registry) {
    if ($Registry.schema_version -ne 1) { throw 'Unsupported registry schema_version.' }
    $numbers = @($Registry.sessions | ForEach-Object { $_.number } | Sort-Object)
    if (($numbers -join ',') -ne '1,2,3,4,5') { throw 'Registry must contain exactly sessions 1 through 5.' }
    $ids = @()
    foreach ($entry in $Registry.sessions) {
        if ([string]::IsNullOrWhiteSpace($entry.role)) { throw 'Every session must have a role.' }
        if ($entry.thread_id) {
            $id = [Guid]::Empty
            if (-not [Guid]::TryParse([string]$entry.thread_id, [ref]$id)) { throw 'Invalid thread_id in registry.' }
            $normalized = $id.ToString()
            if ($ids -contains $normalized) { throw 'Duplicate thread_id in registry.' }
            $ids += $normalized
        }
    }
}

function Write-Utf8File([string]$Path, [string]$Text) {
    [IO.Directory]::CreateDirectory((Split-Path -Parent $Path)) | Out-Null
    [IO.File]::WriteAllText($Path, $Text, (New-Object Text.UTF8Encoding($false)))
}

function Save-SessionRegistry([string]$Root, $Registry) {
    Assert-SessionRegistry $Registry
    Write-Utf8File (Get-LocalRegistryPath $Root) (ConvertTo-Json -InputObject $Registry -Depth 10)
}

function Get-SessionEntry($Registry, [int]$Number) {
    $entries = @($Registry.sessions | Where-Object { $_.number -eq $Number })
    if ($entries.Count -ne 1) { throw 'Session entry is ambiguous or missing.' }
    return $entries[0]
}

function ConvertTo-NativeArgument([string]$Value) {
    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

function Invoke-CodexNative([string]$Binary, [string[]]$Arguments) {
    if (-not [IO.File]::Exists($Binary)) { throw 'Registered Codex executable is missing.' }
    if ([IO.Path]::GetExtension($Binary) -ne '.exe') { throw 'Register the native Codex .exe, not a shell wrapper.' }
    $start = New-Object Diagnostics.ProcessStartInfo
    $start.FileName = $Binary
    $start.Arguments = ($Arguments | ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' '
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.StandardOutputEncoding = [Text.Encoding]::UTF8
    $start.StandardErrorEncoding = [Text.Encoding]::UTF8
    $process = [Diagnostics.Process]::Start($start)
    try {
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(45000)) {
            $process.Kill()
            throw 'Codex timed out. Inspect queue state before retrying.'
        }
        $result = [pscustomobject]@{ exit_code = $process.ExitCode; stdout = $stdout.Result; stderr = $stderr.Result }
        if ($result.exit_code -ne 0) { throw ('Codex failed: ' + $result.stderr + $result.stdout) }
        return $result
    } finally { $process.Dispose() }
}

function Assert-QueueSupport([string]$Binary) {
    $help = Invoke-CodexNative $Binary @('queue', '--help')
    $text = $help.stdout + $help.stderr
    if ($text -notmatch '--thread' -or $text -notmatch '--message') {
        throw 'Installed Codex does not advertise queue --thread and --message support.'
    }
}
