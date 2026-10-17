param(
    [Parameter(Mandatory = $true)][ValidateRange(1, 5)][int]$Session,
    [Parameter(Mandatory = $true)][string]$MessageFile,
    [string]$WorkspaceRoot,
    [switch]$AllowUnverifiedConnectionTest
)
. (Join-Path $PSScriptRoot 'Workspace.Common.ps1')
$root = Resolve-WorkspaceRoot $WorkspaceRoot
$registry = Read-SessionRegistry $root
$entry = Get-SessionEntry $registry $Session
if (-not $entry.thread_id) { throw 'Session has not been registered.' }
if ($entry.verified -ne $true -and -not $AllowUnverifiedConnectionTest) { throw 'Session is unverified. Only an explicit initial connection test may bypass this check.' }
$messagePath = [IO.Path]::GetFullPath($MessageFile)
if (-not [IO.File]::Exists($messagePath)) { throw 'Message file is missing.' }
$strictUtf8 = New-Object Text.UTF8Encoding($false, $true)
$message = $strictUtf8.GetString([IO.File]::ReadAllBytes($messagePath))
if ($message.Length -gt 0 -and $message[0] -eq [char]0xFEFF) { $message = $message.Substring(1) }
if ([string]::IsNullOrWhiteSpace($message)) { throw 'Message file must not be empty.' }
if ($message.IndexOf([char]0) -ge 0) { throw 'Message contains a null character.' }
Assert-QueueSupport $registry.codex_binary
$result = Invoke-CodexNative $registry.codex_binary @('queue', '--thread', $entry.thread_id, '--message', $message)
$receipt = [pscustomobject]@{
    queued_at_utc = [DateTime]::UtcNow.ToString('o'); session = $Session
    thread_id = $entry.thread_id; message_file = $messagePath
    initial_connection_test = [bool]$AllowUnverifiedConnectionTest
    queue_receipt = $result.stdout.Trim(); completed = $false
}
$log = Join-Path $root '.local/dispatch-log.jsonl'
[IO.Directory]::CreateDirectory((Split-Path -Parent $log)) | Out-Null
[IO.File]::AppendAllText($log, ((ConvertTo-Json $receipt -Compress) + "`r`n"), (New-Object Text.UTF8Encoding($false)))
$receipt
