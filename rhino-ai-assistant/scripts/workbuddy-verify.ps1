#Requires -Version 5.1
<#
.SYNOPSIS
Verify one existing candidate and its release gate without rewriting acceptance evidence.
.DESCRIPTION
Exit 2 means BLOCKED, not a successful release. Does not build, install, or launch Rhino/Host.
#>
[CmdletBinding()]
param(
    [string]$SourcePath,
    [Parameter(Mandatory = $true)][string]$RunRoot,
    [string]$Python
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'workbuddy-common.ps1')
$context = $null
try {
    $source = Resolve-WorkbuddySource -SourcePath $SourcePath -DefaultRoot (Split-Path $PSScriptRoot -Parent)
    $run = Resolve-WorkbuddyRunPath -SourceRoot $source -RunRoot $RunRoot -Existing
    $verification = Join-Path $run ('verification/' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '-' + [Guid]::NewGuid().ToString('N'))
    $context = New-WorkbuddyLogContext -Directory $verification
    $pythonTool = Resolve-WorkbuddyPython -Python $Python -Context $context -SourceRoot $source
    $pythonPrefix = @($pythonTool.Prefix) + @('-Xutf8')
    $null = Invoke-WorkbuddyCommand -Context $context -Name 'verify-run' -Executable $pythonTool.Executable -Arguments ($pythonPrefix + @((Join-Path $source 'scripts/workbuddy_evidence.py'), 'verify-run', '--source-root', $source, '--run-root', $run)) -WorkingDirectory $source
    $gate = Invoke-WorkbuddyCommand -Context $context -Name 'release-gate' -Executable $pythonTool.Executable -Arguments ($pythonPrefix + @((Join-Path $source 'scripts/release_gate.py'), (Join-Path $run 'acceptance.local.json'), '--source-root', $source)) -WorkingDirectory $source -AllowedExitCodes @(0, 2)
    $stage2Gate = Invoke-WorkbuddyCommand -Context $context -Name 'stage2-release-gate' -Executable $pythonTool.Executable -Arguments ($pythonPrefix + @((Join-Path $source 'scripts/stage2_gate.py'), (Join-Path $run 'acceptance.stage2.json'), '--source-root', $source)) -WorkingDirectory $source -AllowedExitCodes @(0, 2)
    $combinedExit = [Math]::Max($gate.ExitCode, $stage2Gate.ExitCode)
    Write-WorkbuddyJson -Path (Join-Path $verification 'verification-result.json') -Value ([ordered]@{ source_root = $source; run_root = $run; release_gate_exit_code = $gate.ExitCode; stage2_gate_exit_code = $stage2Gate.ExitCode; production_status = 'REVIEW' })
    Write-Host "Verification logs: $verification"
    if ($gate.ExitCode -eq 2) { Write-Host 'STAGE 1 RELEASE BLOCKED. Verification exits 2; this is not a green release check.' }
    if ($stage2Gate.ExitCode -eq 2) { Write-Host 'STAGE 2 QUALIFICATION BLOCKED. A passing build or fixture never overrides missing model/Rhino qualification.' }
    exit $combinedExit
} catch {
    $message = $_.Exception.Message
    if ($null -ne $context) { Write-WorkbuddyUtf8 -Path (Join-Path $context.Root 'failure.txt') -Text ("FAILED: $message`nOriginal run evidence was preserved.`n") }
    Write-Error -Message $message -ErrorAction Continue
    exit 1
}
