# Shared repository-only helpers. Compatible with Windows PowerShell 5.1 and PowerShell 7.
Set-StrictMode -Version Latest

function Write-WorkbuddyUtf8 {
    param([Parameter(Mandatory = $true)][string]$Path, [AllowEmptyString()][string]$Text)
    [System.IO.File]::WriteAllText($Path, $Text, (New-Object System.Text.UTF8Encoding($false)))
}

function Write-WorkbuddyJson {
    param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)]$Value)
    Write-WorkbuddyUtf8 -Path $Path -Text (ConvertTo-Json -InputObject $Value -Depth 30)
}

function Test-WorkbuddyWindows {
    return [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
}

function Get-WorkbuddyFullPath {
    param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)][string]$BasePath)
    if ([IO.Path]::IsPathRooted($Path)) { return [IO.Path]::GetFullPath($Path) }
    return [IO.Path]::GetFullPath((Join-Path -Path $BasePath -ChildPath $Path))
}

function Assert-WorkbuddyNoReparsePath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $cursor = [IO.Path]::GetFullPath($Path)
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force -ErrorAction Stop
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Symbolic links/junctions are not accepted for source or run paths: $cursor"
            }
        }
        $parent = Split-Path -Path $cursor -Parent
        if ($parent -eq $cursor) { break }
        $cursor = $parent
    }
}

function Resolve-WorkbuddySource {
    param([string]$SourcePath, [Parameter(Mandatory = $true)][string]$DefaultRoot)
    if ([string]::IsNullOrWhiteSpace($SourcePath)) { $SourcePath = $DefaultRoot }
    $root = Get-Item -LiteralPath $SourcePath -Force -ErrorAction Stop
    if (-not $root.PSIsContainer) { throw "SourcePath must be a directory: $SourcePath" }
    Assert-WorkbuddyNoReparsePath -Path $root.FullName
    $pending = New-Object 'System.Collections.Generic.Stack[string]'
    $matches = New-Object 'System.Collections.Generic.List[string]'
    $pending.Push($root.FullName)
    $excluded = @('.git', 'artifacts', 'bin', 'obj', '.runtime', 'node_modules', '__pycache__', '.venv', 'venv')
    while ($pending.Count -gt 0) {
        $directory = $pending.Pop()
        if ((Test-Path -LiteralPath (Join-Path $directory 'RhinoAi.sln') -PathType Leaf) -and
            (Test-Path -LiteralPath (Join-Path $directory 'global.json') -PathType Leaf) -and
            (Test-Path -LiteralPath (Join-Path $directory 'src') -PathType Container)) {
            $matches.Add($directory)
        }
        foreach ($child in @(Get-ChildItem -LiteralPath $directory -Directory -Force -ErrorAction Stop)) {
            if (($excluded -notcontains $child.Name) -and (($child.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0)) {
                $pending.Push($child.FullName)
            }
        }
    }
    if ($matches.Count -eq 0) { throw "No module with RhinoAi.sln, global.json and src was found under $($root.FullName)." }
    if ($matches.Count -ne 1) { throw "Ambiguous SourcePath; pass one module explicitly. Found: $($matches -join '; ')" }
    return $matches[0]
}

function Resolve-WorkbuddyRunPath {
    param([Parameter(Mandatory = $true)][string]$SourceRoot, [string]$RunRoot, [switch]$Existing)
    $allowed = [IO.Path]::GetFullPath((Join-Path $SourceRoot 'artifacts/workbuddy-runs'))
    if ([string]::IsNullOrWhiteSpace($RunRoot)) {
        if ($Existing) { throw 'RunRoot is required for verification.' }
        $RunRoot = Join-Path $allowed (([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')) + '-' + [Guid]::NewGuid().ToString('N'))
    }
    $resolved = Get-WorkbuddyFullPath -Path $RunRoot -BasePath $SourceRoot
    $prefix = $allowed.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    $comparison = [StringComparison]::Ordinal
    if (Test-WorkbuddyWindows) { $comparison = [StringComparison]::OrdinalIgnoreCase }
    if (-not $resolved.StartsWith($prefix, $comparison)) {
        throw "RunRoot must be a child of $allowed. It cannot be the source directory, a sibling, or an outside path."
    }
    Assert-WorkbuddyNoReparsePath -Path $resolved
    if ($Existing) {
        if (-not (Test-Path -LiteralPath $resolved -PathType Container)) { throw "RunRoot does not exist: $resolved" }
    } elseif (Test-Path -LiteralPath $resolved) {
        throw "RunRoot already exists. Choose a new directory; historical evidence is never overwritten: $resolved"
    }
    return $resolved
}

function New-WorkbuddyLogContext {
    param([Parameter(Mandatory = $true)][string]$Directory)
    Assert-WorkbuddyNoReparsePath -Path $Directory
    if (Test-Path -LiteralPath $Directory) { throw "Refusing to reuse log directory: $Directory" }
    $null = New-Item -ItemType Directory -Path $Directory -ErrorAction Stop
    $null = New-Item -ItemType Directory -Path (Join-Path $Directory 'logs') -ErrorAction Stop
    return [pscustomobject]@{ Root = $Directory; Commands = (New-Object 'System.Collections.Generic.List[object]') }
}

function ConvertTo-WorkbuddyNativeArgument {
    param([AllowEmptyString()][string]$Argument)
    # ProcessStartInfo.Arguments uses Windows/CRT-compatible quoting, including trailing backslashes.
    $escaped = [regex]::Replace($Argument, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

function Invoke-WorkbuddyCommand {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Executable,
        [string[]]$Arguments = @(),
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [int[]]$AllowedExitCodes = @(0),
        [switch]$AllowFailure
    )
    $log = Join-Path $Context.Root ('logs/' + $Name + '.log')
    if (Test-Path -LiteralPath $log) { throw "Command log already exists: $log" }
    $started = [DateTime]::UtcNow.ToString('o')
    $commandLine = (ConvertTo-WorkbuddyNativeArgument $Executable) + ' ' + (($Arguments | ForEach-Object { ConvertTo-WorkbuddyNativeArgument $_ }) -join ' ')
    $header = "STARTED_UTC: $started`nWORKING_DIRECTORY: $WorkingDirectory`nCOMMAND: $commandLine`n"
    Write-WorkbuddyUtf8 -Path $log -Text $header
    Write-Host "[$Name] $commandLine"
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = New-Object System.Diagnostics.ProcessStartInfo
    $process.StartInfo.FileName = $Executable
    $process.StartInfo.Arguments = ($Arguments | ForEach-Object { ConvertTo-WorkbuddyNativeArgument $_ }) -join ' '
    $process.StartInfo.WorkingDirectory = $WorkingDirectory
    $process.StartInfo.UseShellExecute = $false
    $process.StartInfo.CreateNoWindow = $true
    $process.StartInfo.RedirectStandardOutput = $true
    $process.StartInfo.RedirectStandardError = $true
    $process.StartInfo.StandardOutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $process.StartInfo.StandardErrorEncoding = New-Object System.Text.UTF8Encoding($false)
    # Child-process settings only. No persistent environment, credential or security changes.
    $process.StartInfo.EnvironmentVariables['DOTNET_CLI_TELEMETRY_OPTOUT'] = '1'
    $process.StartInfo.EnvironmentVariables['DOTNET_SKIP_FIRST_TIME_EXPERIENCE'] = '1'
    $process.StartInfo.EnvironmentVariables['DOTNET_CLI_UI_LANGUAGE'] = 'en-US'
    $process.StartInfo.EnvironmentVariables['PYTHONDONTWRITEBYTECODE'] = '1'
    $stdout = ''; $stderr = ''; $code = -1
    try {
        if (-not $process.Start()) { throw 'The operating system did not start the command.' }
        # Read both pipes concurrently. Native stderr is data, not a PowerShell terminating error.
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        $stdout = $stdoutTask.GetAwaiter().GetResult()
        $stderr = $stderrTask.GetAwaiter().GetResult()
        $code = $process.ExitCode
    } catch {
        $stderr += "`nCOMMAND_START_OR_CAPTURE_ERROR: $($_.Exception.Message)"
    } finally {
        $process.Dispose()
        $finished = [DateTime]::UtcNow.ToString('o')
        Write-WorkbuddyUtf8 -Path $log -Text ($header + "STDOUT:`n$stdout`nSTDERR:`n$stderr`nFINISHED_UTC: $finished`nEXIT_CODE: $code`n")
        $Context.Commands.Add([pscustomobject]@{ name = $Name; exit_code = $code; log = ('logs/' + $Name + '.log'); started_utc = $started; finished_utc = $finished })
        Write-WorkbuddyJson -Path (Join-Path $Context.Root 'commands.json') -Value @($Context.Commands.ToArray())
    }
    if ($stdout) { Write-Host $stdout.TrimEnd() }
    if ($stderr) { Write-Host $stderr.TrimEnd() }
    Write-Host "[$Name] EXIT_CODE: $code"
    if ((-not $AllowFailure) -and ($AllowedExitCodes -notcontains $code)) {
        throw "Command '$Name' failed with exit code $code. Preserved log: $log"
    }
    return [pscustomobject]@{ ExitCode = $code; Stdout = $stdout; Stderr = $stderr; Log = $log }
}

function Resolve-WorkbuddyExecutable {
    param([Parameter(Mandatory = $true)][string]$Name)
    $command = Get-Command -Name $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $command) { throw "Executable not found: $Name. Install the documented prerequisite yourself; this workflow does not install software." }
    return $command.Source
}

function Resolve-WorkbuddyPython {
    param([string]$Python, [Parameter(Mandatory = $true)]$Context, [Parameter(Mandatory = $true)][string]$SourceRoot)
    $candidates = @('py', 'python3', 'python')
    if (-not [string]::IsNullOrWhiteSpace($Python)) { $candidates = @($Python) }
    $index = 0
    foreach ($candidate in $candidates) {
        $index++
        $command = Get-Command -Name $candidate -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -eq $command) { continue }
        $prefix = @()
        if ([IO.Path]::GetFileNameWithoutExtension($command.Source) -eq 'py') { $prefix = @('-3') }
        $probe = Invoke-WorkbuddyCommand -Context $Context -Name "python-version-$index" -Executable $command.Source -Arguments ($prefix + @('-Xutf8', '-c', 'import sys; print(sys.version); raise SystemExit(0 if sys.version_info >= (3, 10) else 1)')) -WorkingDirectory $SourceRoot -AllowFailure
        if ($probe.ExitCode -eq 0) { return [pscustomobject]@{ Executable = $command.Source; Prefix = $prefix } }
    }
    throw 'Python 3.10+ was not found. Supply -Python with the path to python.exe or py.exe; arguments are not accepted in that parameter.'
}

function Get-WorkbuddySourceCommit {
    param([string]$SourceCommit, [Parameter(Mandatory = $true)]$Context, [Parameter(Mandatory = $true)][string]$SourceRoot)
    if ($SourceCommit -and $SourceCommit -notmatch '^[0-9a-fA-F]{40}$') { throw 'SourceCommit must be a full 40-character Git commit hash.' }
    $git = Get-Command -Name git -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $git) {
        # A downloaded archive can be inside an unrelated checkout. Only tracked
        # module markers establish that this checkout owns the selected module.
        $tracked = Invoke-WorkbuddyCommand -Context $Context -Name 'source-git-tracked' -Executable $git.Source -Arguments @('-C', $SourceRoot, 'ls-files', '--error-unmatch', '--', 'RhinoAi.sln', 'global.json', 'src/RhinoAi.Host/RhinoAi.Host.csproj') -WorkingDirectory $SourceRoot -AllowFailure
        if ($tracked.ExitCode -ne 0) {
            if ($SourceCommit) { return $SourceCommit.ToLowerInvariant() }
            return $null
        }
        $result = Invoke-WorkbuddyCommand -Context $Context -Name 'source-git-head' -Executable $git.Source -Arguments @('-C', $SourceRoot, 'rev-parse', '--verify', 'HEAD') -WorkingDirectory $SourceRoot -AllowFailure
        if ($result.ExitCode -eq 0) {
            $head = $result.Stdout.Trim()
            if ($head -notmatch '^[0-9a-fA-F]{40}$') { throw 'Git did not return a valid full HEAD commit.' }
            if ($SourceCommit -and $SourceCommit -ne $head) { throw 'SourceCommit does not match the actual Git HEAD. Archive provenance cannot override an available checkout HEAD.' }
            return $head.ToLowerInvariant()
        }
    }
    if ($SourceCommit) { return $SourceCommit.ToLowerInvariant() }
    return $null
}

function Assert-WorkbuddyPrerequisites {
    param([Parameter(Mandatory = $true)]$Context, [Parameter(Mandatory = $true)][string]$SourceRoot, [Parameter(Mandatory = $true)][string]$Dotnet, [switch]$CrossBuild)
    $sdk = Get-Content -LiteralPath (Join-Path $SourceRoot 'global.json') -Raw | ConvertFrom-Json
    if ($sdk.sdk.version -ne '8.0.425' -or $sdk.sdk.rollForward -ne 'latestPatch') { throw 'Expected global.json SDK 8.0.425 with rollForward latestPatch.' }
    $version = Invoke-WorkbuddyCommand -Context $Context -Name 'dotnet-version' -Executable $Dotnet -Arguments @('--version') -WorkingDirectory $SourceRoot
    if ($version.Stdout.Trim() -notmatch '^8\.0\.(4[0-9]{2})$') { throw 'The selected SDK must be stable 8.0.4xx, as resolved from the module global.json.' }
    if ([int]$Matches[1] -lt 425) { throw 'The selected SDK must be at least 8.0.425 and below 8.0.500.' }
    $info = Invoke-WorkbuddyCommand -Context $Context -Name 'dotnet-info' -Executable $Dotnet -Arguments @('--info') -WorkingDirectory $SourceRoot
    $runtimes = Invoke-WorkbuddyCommand -Context $Context -Name 'dotnet-runtimes' -Executable $Dotnet -Arguments @('--list-runtimes') -WorkingDirectory $SourceRoot
    if ($runtimes.Stdout -notmatch '(?m)^Microsoft\.NETCore\.App 8\.0\.\d+ \[' -or
        $runtimes.Stdout -notmatch '(?m)^Microsoft\.AspNetCore\.App 8\.0\.\d+ \[') {
        throw 'Microsoft.NETCore.App 8.0 and Microsoft.AspNetCore.App 8.0 are required for the automated Core/Host tests.'
    }
    if (-not $CrossBuild) {
        if (-not (Test-WorkbuddyWindows)) { throw 'Native candidate validation requires Windows x64. Use -CrossBuild only for headless cross-build checks; live Rhino stays NOT_RUN.' }
        if (-not [Environment]::Is64BitOperatingSystem -or -not [Environment]::Is64BitProcess -or $info.Stdout -notmatch '(?im)^\s*Architecture:\s*x64\s*$' -or $info.Stdout -notmatch '(?im)^\s*RID:\s*win-x64\s*$') {
            throw 'Use Windows x64, a 64-bit PowerShell process, and the x64 .NET 8 SDK/runtime.'
        }
    }
    return [pscustomobject]@{ sdk_version = $version.Stdout.Trim(); platform = [Environment]::OSVersion.VersionString; process_64_bit = [Environment]::Is64BitProcess; cross_build = [bool]$CrossBuild; live_windows_rhino = 'NOT_RUN' }
}
