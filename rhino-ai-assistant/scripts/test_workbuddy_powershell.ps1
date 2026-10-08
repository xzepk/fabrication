#Requires -Version 5.1
# Self-tests for the PowerShell wrappers. They never build or load Rhino/Host.
[CmdletBinding()]
param([string]$TestRoot)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'workbuddy-common.ps1')
if (-not $TestRoot) { $TestRoot = Join-Path ([IO.Path]::GetTempPath()) ('workbuddy-ps-tests-' + [Guid]::NewGuid().ToString('N')) }
if (Test-Path -LiteralPath $TestRoot) { throw 'Self-test TestRoot must be new.' }
$null = New-Item -ItemType Directory -Path $TestRoot -ErrorAction Stop
$script:passed = 0
$script:failed = 0
$script:results = New-Object 'System.Collections.Generic.List[object]'
function Assert-True { param([bool]$Value, [string]$Message) if (-not $Value) { throw $Message } }
function Assert-Throws {
    param([scriptblock]$Action, [string]$Pattern)
    try { & $Action } catch { if ($_.Exception.Message -match $Pattern) { return }; throw }
    throw "Expected rejection matching: $Pattern"
}
function Test-Case {
    param([string]$Name, [scriptblock]$Action)
    try {
        & $Action
        $script:passed++
        $script:results.Add([pscustomobject]@{ name = $Name; status = 'PASS' })
        Write-Host "PASS $Name"
    } catch {
        $script:failed++
        $script:results.Add([pscustomobject]@{ name = $Name; status = 'FAIL'; error = $_.Exception.Message })
        Write-Host "FAIL ${Name}: $($_.Exception.Message)"
    }
}
function New-MarkerModule {
    param([string]$Root)
    $null = New-Item -ItemType Directory -Path (Join-Path $Root 'src') -ErrorAction Stop
    Write-WorkbuddyUtf8 -Path (Join-Path $Root 'RhinoAi.sln') -Text 'fixture'
    Write-WorkbuddyUtf8 -Path (Join-Path $Root 'global.json') -Text '{"sdk":{"version":"8.0.425","rollForward":"latestPatch"}}'
}
$unicode = [string][char]0x6D4B + [char]0x8BD5
$fixture = Join-Path $TestRoot ('source with spaces ' + $unicode)
$module = Join-Path $fixture 'archive/repository/rhino-ai-assistant'
New-MarkerModule $module
Test-Case 'all shipped PowerShell scripts parse' {
    foreach ($file in @(Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*workbuddy*.ps1')) {
        $tokens = $null; $parseErrors = $null
        $null = [System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$parseErrors)
        Assert-True ($parseErrors.Count -eq 0) ($file.Name + ': ' + ($parseErrors -join '; '))
    }
}
Test-Case 'source resolves from extracted parent with spaces and Unicode' {
    Assert-True ((Resolve-WorkbuddySource -SourcePath $fixture -DefaultRoot $PSScriptRoot) -eq $module) 'Incorrect extracted parent resolution'
}
Test-Case 'source resolves from module and ignores current directory' {
    Assert-True ((Resolve-WorkbuddySource -DefaultRoot $module) -eq $module) 'Incorrect default/module resolution'
}
Test-Case 'missing source markers are rejected' {
    $missing = Join-Path $TestRoot 'empty'
    $null = New-Item -ItemType Directory -Path $missing
    Assert-Throws { Resolve-WorkbuddySource -SourcePath $missing -DefaultRoot $PSScriptRoot } 'No module'
}
Test-Case 'artifact copies do not make source ambiguous' {
    New-MarkerModule (Join-Path $module 'artifacts/copied-module')
    Assert-True ((Resolve-WorkbuddySource -SourcePath $fixture -DefaultRoot $PSScriptRoot) -eq $module) 'Artifact directory was scanned'
}
Test-Case 'ambiguous extracted parents are rejected' {
    New-MarkerModule (Join-Path $fixture 'second/module')
    Assert-Throws { Resolve-WorkbuddySource -SourcePath $fixture -DefaultRoot $PSScriptRoot } 'Ambiguous'
}
Test-Case 'default run names are unique and under module artifacts' {
    $one = Resolve-WorkbuddyRunPath -SourceRoot $module
    $two = Resolve-WorkbuddyRunPath -SourceRoot $module
    Assert-True ($one -ne $two) 'Default run names collided'
    Assert-True ($one.StartsWith((Join-Path $module 'artifacts/workbuddy-runs'))) 'Run escaped module'
}
Test-Case 'relative run paths resolve against module' {
    $actual = Resolve-WorkbuddyRunPath -SourceRoot $module -RunRoot 'artifacts/workbuddy-runs/my run'
    Assert-True ($actual -eq (Join-Path $module 'artifacts/workbuddy-runs/my run')) 'Relative run path used current directory'
}
Test-Case 'outside and traversal run paths are rejected' {
    Assert-Throws { Resolve-WorkbuddyRunPath -SourceRoot $module -RunRoot $TestRoot } 'must be a child'
    Assert-Throws { Resolve-WorkbuddyRunPath -SourceRoot $module -RunRoot 'artifacts/workbuddy-runs/../../../outside' } 'must be a child'
    Assert-Throws { Resolve-WorkbuddyRunPath -SourceRoot $module -RunRoot 'artifacts/workbuddy-runs' } 'must be a child'
    Assert-Throws { Resolve-WorkbuddyRunPath -SourceRoot $module -RunRoot 'artifacts/workbuddy-runs-sibling/run' } 'must be a child'
}
Test-Case 'existing run evidence is never reused' {
    $existing = Join-Path $module 'artifacts/workbuddy-runs/existing'
    $null = New-Item -ItemType Directory -Path $existing
    Write-WorkbuddyUtf8 -Path (Join-Path $existing 'preserve.txt') -Text 'existing evidence'
    Assert-Throws { Resolve-WorkbuddyRunPath -SourceRoot $module -RunRoot $existing } 'already exists'
    Assert-True ((Resolve-WorkbuddyRunPath -SourceRoot $module -RunRoot $existing -Existing) -eq $existing) 'Read-only verification path rejected'
    Assert-True (([IO.File]::ReadAllText((Join-Path $existing 'preserve.txt'))) -eq 'existing evidence') 'Existing evidence changed'
}
Test-Case 'JSON is UTF-8 without BOM' {
    $path = Join-Path $TestRoot 'unicode.json'
    Write-WorkbuddyJson -Path $path -Value ([ordered]@{ value = $unicode })
    $bytes = [IO.File]::ReadAllBytes($path)
    Assert-True (-not ($bytes.Length -ge 3 -and $bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191)) 'UTF-8 BOM found'
    Assert-True (([IO.File]::ReadAllText($path, [Text.Encoding]::UTF8) | ConvertFrom-Json).value -eq $unicode) 'Unicode JSON did not round trip'
}
$powershellName = 'pwsh'
if (Test-WorkbuddyWindows) { $powershellName = 'pwsh.exe' }
if ($PSVersionTable.PSEdition -eq 'Desktop') { $powershellName = 'powershell.exe' }
$powershellExe = Join-Path $PSHOME $powershellName
$probeScript = Join-Path $TestRoot 'native probe.ps1'
Write-WorkbuddyUtf8 -Path $probeScript -Text @'
param([string]$One, [string]$Two, [string]$Three, [int]$ExitCode = 0)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::Out.WriteLine((ConvertTo-Json -InputObject @($One, $Two, $Three) -Compress))
[Console]::Error.WriteLine('stderr is captured as data')
exit $ExitCode
'@
$nativeContext = New-WorkbuddyLogContext -Directory (Join-Path $TestRoot 'native-command-logs')
Test-Case 'native arguments preserve spaces quotes backslashes and Unicode' {
    $expected = @(('path with spaces ' + $unicode), 'embedded"quote', 'trailing\')
    $result = Invoke-WorkbuddyCommand -Context $nativeContext -Name 'argument-probe' -Executable $powershellExe -Arguments (@('-NoProfile', '-NonInteractive', '-File', $probeScript, '-One', $expected[0], '-Two', $expected[1], '-Three', $expected[2])) -WorkingDirectory $TestRoot
    $actual = $result.Stdout.Trim() | ConvertFrom-Json
    Assert-True ($actual.Count -eq 3) 'Expected three native arguments'
    for ($i = 0; $i -lt 3; $i++) { Assert-True ($actual[$i] -ceq $expected[$i]) "Argument $i changed" }
    Assert-True ($result.Stderr.Contains('stderr is captured as data')) 'stderr was not captured'
    Assert-True ([IO.File]::ReadAllText($result.Log).Contains('EXIT_CODE: 0')) 'Exit code absent from log'
}
Test-Case 'nonzero native exits fail immediately and preserve logs' {
    Assert-Throws { Invoke-WorkbuddyCommand -Context $nativeContext -Name 'failure-probe' -Executable $powershellExe -Arguments @('-NoProfile', '-NonInteractive', '-File', $probeScript, '-ExitCode', '7') -WorkingDirectory $TestRoot } 'failed with exit code 7'
    $ledger = Get-Content -LiteralPath (Join-Path $nativeContext.Root 'commands.json') -Raw | ConvertFrom-Json
    Assert-True (@($ledger | Where-Object { $_.name -eq 'failure-probe' -and $_.exit_code -eq 7 }).Count -eq 1) 'Failed command not recorded'
    Assert-True ([IO.File]::ReadAllText((Join-Path $nativeContext.Root 'logs/failure-probe.log')).Contains('EXIT_CODE: 7')) 'Failure log missing'
}
Test-Case 'gate exit 2 is explicitly preserved rather than replaced with 0' {
    $result = Invoke-WorkbuddyCommand -Context $nativeContext -Name 'gate-probe' -Executable $powershellExe -Arguments @('-NoProfile', '-NonInteractive', '-File', $probeScript, '-ExitCode', '2') -WorkingDirectory $TestRoot -AllowedExitCodes @(0, 2)
    Assert-True ($result.ExitCode -eq 2) 'Gate exit code was swallowed'
}
Test-Case 'duplicate command names never overwrite earlier logs' {
    $before = [IO.File]::ReadAllText((Join-Path $nativeContext.Root 'logs/gate-probe.log'))
    Assert-Throws { Invoke-WorkbuddyCommand -Context $nativeContext -Name 'gate-probe' -Executable $powershellExe -Arguments @('-NoProfile', '-NonInteractive', '-File', $probeScript) -WorkingDirectory $TestRoot } 'already exists'
    Assert-True ([IO.File]::ReadAllText((Join-Path $nativeContext.Root 'logs/gate-probe.log')) -ceq $before) 'Historical command log changed'
}
Write-WorkbuddyJson -Path (Join-Path $TestRoot 'results.json') -Value ([ordered]@{ passed = $script:passed; failed = $script:failed; powershell_version = $PSVersionTable.PSVersion.ToString(); platform = [Environment]::OSVersion.VersionString; tests = @($script:results.ToArray()) })
Write-Host "PowerShell helpers: $script:passed PASS, $script:failed FAIL. Fixtures/logs preserved: $TestRoot"
if ($script:failed -gt 0) { exit 1 }
exit 0
