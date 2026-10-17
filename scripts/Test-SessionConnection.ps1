param(
    [Parameter(Mandatory = $true)][ValidateRange(1, 5)][int]$Session,
    [string]$WorkspaceRoot,
    [switch]$PrepareOnly
)
. (Join-Path $PSScriptRoot 'Workspace.Common.ps1')
$root = Resolve-WorkspaceRoot $WorkspaceRoot
$registry = Read-SessionRegistry $root
$entry = Get-SessionEntry $registry $Session
if (-not $entry.thread_id) { throw 'Register the session before preparing a connection test.' }
$nonce = [Guid]::NewGuid().ToString('N')
$ackRelative = ".local/session-acks/session-$Session-$nonce.json"
$challengePath = Join-Path $root ".local/session-tests/session-$Session.json"
$messagePath = Join-Path $root ".local/session-tests/session-$Session-$nonce.txt"
$challenge = [pscustomobject]@{
    session = $Session; thread_id = $entry.thread_id; nonce = $nonce
    ack_path = $ackRelative; created_at_utc = [DateTime]::UtcNow.ToString('o'); queued = $false
}
$ack = [pscustomobject]@{ session = $Session; thread_id = $entry.thread_id; nonce = $nonce }
$ackFullPath = Join-Path $root $ackRelative
$message = @"
Initial connection test for session $Session. Read AGENTS.md and your session role first.
Only if this conversation's actual thread ID is $($entry.thread_id), write the following UTF-8 JSON to:
$ackFullPath
$(ConvertTo-Json $ack -Compress)
Do not edit production files or send messages to other sessions. This acknowledgement confirms receipt only, not task completion.
"@
Write-Utf8File $challengePath (ConvertTo-Json $challenge -Depth 5)
Write-Utf8File $messagePath $message
if (-not $PrepareOnly) {
    & (Join-Path $PSScriptRoot 'Send-SessionMessage.ps1') -Session $Session -MessageFile $messagePath -WorkspaceRoot $root -AllowUnverifiedConnectionTest | Out-Null
    $challenge.queued = $true
    Write-Utf8File $challengePath (ConvertTo-Json $challenge -Depth 5)
}
[pscustomobject]@{ session = $Session; queued = $challenge.queued; message_file = $messagePath; expected_ack = $ackFullPath; verified = $false }
