#Requires -Version 5.1
<#
.SYNOPSIS
Build a fresh repository-only candidate and headless evidence; never installs or loads Rhino.
.PARAMETER SourcePath
Module root, repository root, or extracted parent containing exactly one RhinoAi module.
.PARAMETER RunRoot
New run directory below <module>/artifacts/workbuddy-runs. Relative paths use the module root.
.PARAMETER CrossBuild
Explicit headless cross-build mode; it never grants live Windows/Rhino acceptance.
#>
[CmdletBinding()]
param(
    [string]$SourcePath,
    [string]$RunRoot,
    [string]$Dotnet = 'dotnet',
    [string]$Python,
    [string]$SourceCommit,
    [switch]$CrossBuild
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'workbuddy-common.ps1')
$context = $null
try {
    $source = Resolve-WorkbuddySource -SourcePath $SourcePath -DefaultRoot (Split-Path $PSScriptRoot -Parent)
    $run = Resolve-WorkbuddyRunPath -SourceRoot $source -RunRoot $RunRoot
    $context = New-WorkbuddyLogContext -Directory $run
    Write-Host "Source module: $source"
    Write-Host "New run: $run"
    $dotnetExe = Resolve-WorkbuddyExecutable -Name $Dotnet
    $pythonTool = Resolve-WorkbuddyPython -Python $Python -Context $context -SourceRoot $source
    $pythonPrefix = @($pythonTool.Prefix) + @('-Xutf8')
    $commit = Get-WorkbuddySourceCommit -SourceCommit $SourceCommit -Context $context -SourceRoot $source
    $preflight = Assert-WorkbuddyPrerequisites -Context $context -SourceRoot $source -Dotnet $dotnetExe -CrossBuild:$CrossBuild
    Write-WorkbuddyJson -Path (Join-Path $run 'environment.json') -Value ([ordered]@{
        source_root = $source; source_commit = $commit; sdk_version = $preflight.sdk_version
        platform = $preflight.platform; process_64_bit = $preflight.process_64_bit
        cross_build = [bool]$CrossBuild; live_windows_rhino = 'NOT_RUN'
        dotnet = $dotnetExe; python = $pythonTool.Executable
        note = 'Prerequisites and headless tests do not establish live Windows/Rhino qualification.'
    })
    $helper = Join-Path $source 'scripts/workbuddy_evidence.py'
    $null = Invoke-WorkbuddyCommand -Context $context -Name 'source-verify' -Executable $pythonTool.Executable -Arguments ($pythonPrefix + @($helper, 'verify-source', '--source-root', $source)) -WorkingDirectory $source
    $null = Invoke-WorkbuddyCommand -Context $context -Name 'restore' -Executable $dotnetExe -Arguments @('restore', 'RhinoAi.sln', '--locked-mode', '--source', 'https://api.nuget.org/v3/index.json', '-m:1') -WorkingDirectory $source
    $null = Invoke-WorkbuddyCommand -Context $context -Name 'build' -Executable $dotnetExe -Arguments @('build', 'RhinoAi.sln', '--no-restore', '-c', 'Release', '-m:1') -WorkingDirectory $source
    $null = Invoke-WorkbuddyCommand -Context $context -Name 'core-tests' -Executable $dotnetExe -Arguments @((Join-Path $source 'tests/RhinoAi.Core.Tests/bin/Release/net8.0/RhinoAi.Core.Tests.dll')) -WorkingDirectory $source
    $hostDll = Join-Path $source 'src/RhinoAi.Host/bin/Release/net8.0/RhinoAi.Host.dll'
    $null = Invoke-WorkbuddyCommand -Context $context -Name 'host-tests' -Executable $dotnetExe -Arguments @((Join-Path $source 'tests/RhinoAi.Host.IntegrationTests/bin/Release/net8.0/RhinoAi.Host.IntegrationTests.dll'), $dotnetExe, $hostDll, (Join-Path $run 'host-integration')) -WorkingDirectory $source
    $null = Invoke-WorkbuddyCommand -Context $context -Name 'release-gate-tests' -Executable $pythonTool.Executable -Arguments ($pythonPrefix + @((Join-Path $source 'scripts/test_release_gate.py'))) -WorkingDirectory $source
    $null = Invoke-WorkbuddyCommand -Context $context -Name 'workbuddy-evidence-tests' -Executable $pythonTool.Executable -Arguments ($pythonPrefix + @((Join-Path $source 'scripts/test_workbuddy_evidence.py'))) -WorkingDirectory $source
    $powershellName = 'pwsh'
    if (Test-WorkbuddyWindows) { $powershellName = 'pwsh.exe' }
    if ($PSVersionTable.PSEdition -eq 'Desktop') { $powershellName = 'powershell.exe' }
    $powershellExe = Join-Path $PSHOME $powershellName
    $null = Invoke-WorkbuddyCommand -Context $context -Name 'powershell-tests' -Executable $powershellExe -Arguments @('-NoProfile', '-NonInteractive', '-File', (Join-Path $source 'scripts/test_workbuddy_powershell.ps1'), '-TestRoot', (Join-Path $run 'powershell-tests')) -WorkingDirectory $source
    $hostProject = 'src/RhinoAi.Host/RhinoAi.Host.csproj'
    $null = Invoke-WorkbuddyCommand -Context $context -Name 'publish-restore' -Executable $dotnetExe -Arguments @('restore', $hostProject, '-r', 'win-x64', '--locked-mode', '--source', 'https://api.nuget.org/v3/index.json', '-p:NuGetLockFilePath=packages.win-x64.lock.json', '-m:1') -WorkingDirectory $source
    $hostOutput = Join-Path $run 'candidate/host'
    $pluginOutput = Join-Path $run 'candidate/plugin'
    $null = Invoke-WorkbuddyCommand -Context $context -Name 'publish' -Executable $dotnetExe -Arguments @('publish', $hostProject, '--no-restore', '-c', 'Release', '-r', 'win-x64', '--self-contained', 'false', '-p:UseAppHost=true', '-p:NuGetLockFilePath=packages.win-x64.lock.json', '-o', $hostOutput, '-m:1') -WorkingDirectory $source
    $null = New-Item -ItemType Directory -Path $pluginOutput -ErrorAction Stop
    foreach ($name in @('RhinoAi.Plugin.rhp', 'RhinoAi.Plugin.deps.json', 'RhinoAi.Core.dll', 'RhinoAi.Contracts.dll')) {
        $inputFile = Join-Path $source ('src/RhinoAi.Plugin/bin/Release/net8.0-windows/' + $name)
        if (-not (Test-Path -LiteralPath $inputFile -PathType Leaf)) { throw "Required plugin file is missing: $inputFile" }
        Copy-Item -LiteralPath $inputFile -Destination (Join-Path $pluginOutput $name) -ErrorAction Stop
    }
    foreach ($name in @('RhinoAi.Host.exe', 'RhinoAi.Host.dll', 'RhinoAi.Host.deps.json', 'RhinoAi.Host.runtimeconfig.json', 'RhinoAi.Core.dll', 'RhinoAi.Contracts.dll')) {
        if (-not (Test-Path -LiteralPath (Join-Path $hostOutput $name) -PathType Leaf)) { throw "Required framework-dependent Host file is missing: $name" }
    }
    $initArguments = $pythonPrefix + @($helper, 'init', '--source-root', $source, '--run-root', $run)
    if ($commit) { $initArguments += @('--source-commit', $commit) }
    $null = Invoke-WorkbuddyCommand -Context $context -Name 'evidence-init' -Executable $pythonTool.Executable -Arguments $initArguments -WorkingDirectory $source
    $gate = Invoke-WorkbuddyCommand -Context $context -Name 'release-gate' -Executable $pythonTool.Executable -Arguments ($pythonPrefix + @((Join-Path $source 'scripts/release_gate.py'), (Join-Path $run 'acceptance.local.json'), '--source-root', $source)) -WorkingDirectory $source -AllowedExitCodes @(0, 2)
    Write-WorkbuddyJson -Path (Join-Path $run 'build-result.json') -Value ([ordered]@{
        build_and_headless_tests = 'PASS'; build_exit_code = 0; release_gate_exit_code = $gate.ExitCode
        release_status = $(if ($gate.ExitCode -eq 0) { 'TECHNICAL_ACCEPTANCE_PASSED' } else { 'BLOCKED' })
        live_windows_rhino = 'NOT_RUN'; production_status = 'REVIEW'; cross_build = [bool]$CrossBuild
        source_root = $source; candidate = (Join-Path $run 'candidate'); acceptance = (Join-Path $run 'acceptance.local.json')
    })
    Write-Host "Build and headless tests: PASS. Candidate: $(Join-Path $run 'candidate')"
    if ($gate.ExitCode -eq 2) { Write-Host 'STAGE 1 RELEASE BLOCKED (exit 2). F-02 through F-11 require live Windows/Rhino evidence. Build command exits 0 only for successful build/headless tests.' }
    else { Write-Host 'STAGE 1 TECHNICAL ACCEPTANCE PASSED; production status remains REVIEW.' }
    Write-Host "Acceptance report: $(Join-Path $run 'acceptance.local.json')"
    Write-Host 'No candidate Host or Rhino plugin was installed or launched. Host integration tests use isolated test processes.'
    exit 0
} catch {
    $message = $_.Exception.Message
    if ($null -ne $context) {
        Write-WorkbuddyUtf8 -Path (Join-Path $context.Root 'failure.txt') -Text ("FAILED: $message`nEvidence and logs were preserved. No cleanup was attempted.`n")
        Write-Host "Logs preserved: $($context.Root)"
    }
    Write-Error -Message $message -ErrorAction Continue
    exit 1
}
