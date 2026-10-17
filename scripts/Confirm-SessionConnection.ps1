param(
    [Parameter(Mandatory = $true)][ValidateRange(1, 5)][int]$Session,
    [string]$WorkspaceRoot
)
. (Join-Path $PSScriptRoot 'Workspace.Common.ps1')
$root = Resolve-WorkspaceRoot $WorkspaceRoot
$registry = Read-SessionRegistry $root
$entry = Get-SessionEntry $registry $Session
$challengePath = Join-Path $root ".local/session-tests/session-$Session.json"
if (-not [IO.File]::Exists($challengePath)) { throw 'Connection challenge is missing.' }
$challenge = [IO.File]::ReadAllText($challengePath, [Text.Encoding]::UTF8) | ConvertFrom-Json
if ($challenge.queued -ne $true) { throw 'Connection challenge was not queued. Prepared-only messages cannot verify a connection.' }
if ($challenge.session -ne $Session -or $challenge.thread_id -ne $entry.thread_id) { throw 'Challenge does not match the currently registered session.' }
$expectedPath = ".local/session-acks/session-$Session-$($challenge.nonce).json"
if ($challenge.nonce -notmatch '^[a-f0-9]{32}$' -or $challenge.ack_path -ne $expectedPath) { throw 'Invalid challenge acknowledgement path.' }
$ackPath = Join-Path $root $expectedPath
if (-not [IO.File]::Exists($ackPath)) { throw 'Recipient acknowledgement is missing. Check the actual receiving session.' }
$ack = [IO.File]::ReadAllText($ackPath, [Text.Encoding]::UTF8) | ConvertFrom-Json
if ($ack.session -ne $Session -or $ack.thread_id -ne $entry.thread_id -or $ack.nonce -cne $challenge.nonce) { throw 'Acknowledgement does not match the pending challenge.' }
$entry.verified = $true
$entry.ack_path = $expectedPath
Save-SessionRegistry $root $registry
[pscustomobject]@{ session = $Session; verified = $true; ack_path = $expectedPath; task_completed = $false }
