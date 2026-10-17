param(
    [Parameter(Mandatory = $true)][ValidateRange(1, 5)][int]$Session,
    [Parameter(Mandatory = $true)][Guid]$ThreadId,
    [string]$WorkspaceRoot
)
. (Join-Path $PSScriptRoot 'Workspace.Common.ps1')
$root = Resolve-WorkspaceRoot $WorkspaceRoot
if ($ThreadId -eq [Guid]::Empty) { throw 'ThreadId must not be the empty GUID.' }
$registry = Read-SessionRegistry $root
$entry = Get-SessionEntry $registry $Session
$normalized = $ThreadId.ToString()
foreach ($other in $registry.sessions) {
    if ($other.number -ne $Session -and $other.thread_id -and ([Guid]$other.thread_id).ToString() -eq $normalized) { throw 'ThreadId is already registered to another session.' }
}
$entry.thread_id = $normalized
$entry.verified = $false
$entry.ack_path = $null
# A registration requires a fresh test, even when the same thread is registered again.
$oldChallenge = Join-Path $root ".local/session-tests/session-$Session.json"
if ([IO.File]::Exists($oldChallenge)) { [IO.File]::Delete($oldChallenge) }
Save-SessionRegistry $root $registry
[pscustomobject]@{ session = $Session; role = $entry.role; verified = $false; next_step = 'Run Test-SessionConnection.ps1, then confirm the received acknowledgement.' }
