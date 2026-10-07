param(
  [string]$Venv = $(if ($env:CLADDING_VENV) { $env:CLADDING_VENV } else { Join-Path $env:LOCALAPPDATA "cladding-delivery\venv" }),
  [string]$Extras = ""
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$RootFull = [IO.Path]::GetFullPath($Root).TrimEnd('\')
$VenvFull = [IO.Path]::GetFullPath($Venv).TrimEnd('\')
if (($VenvFull + '\').StartsWith($RootFull + '\', [StringComparison]::OrdinalIgnoreCase)) {
  throw "Runtime must be external to the skill package: $VenvFull"
}
if (-not (Test-Path (Join-Path $VenvFull 'pyvenv.cfg'))) {
  python -m venv $VenvFull
  if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed" }
}
$Python = Join-Path $VenvFull "Scripts\python.exe"
& $Python -m pip install -U pip
if ($LASTEXITCODE -ne 0) { throw "pip setup failed" }
$Stage = Join-Path ([IO.Path]::GetTempPath()) ("cladding-install-" + [guid]::NewGuid().ToString('N'))
try {
  New-Item -ItemType Directory -Path $Stage | Out-Null
  $StagedSource = Join-Path $Stage 'cladding-delivery'
  Copy-Item -Path $Root -Destination $StagedSource -Recurse
  $InstallTarget = if ($Extras) { "$StagedSource[$Extras]" } else { $StagedSource }
  & $Python -m pip install $InstallTarget
  if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }
} finally {
  if (Test-Path $Stage) { Remove-Item -LiteralPath $Stage -Recurse -Force }
}
Write-Host "External Python runtime: $VenvFull"
Write-Host "Optional provider: -Extras build123d (or build123d,test). ODA is never required."
Write-Host "For DWG build ACadSharp into an EXTERNAL work directory; see references/operations.md."
