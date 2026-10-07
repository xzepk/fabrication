$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Venv = Join-Path $Root ".venv"
python -m venv $Venv
& (Join-Path $Venv "Scripts\python.exe") -m pip install -U pip
& (Join-Path $Venv "Scripts\python.exe") -m pip install -e $Root
Write-Host "Python environment ready: $Venv"
if (Get-Command dotnet -ErrorAction SilentlyContinue) {
  Write-Host "dotnet found: $(dotnet --version)"
  Write-Host "Build DWG helper: dotnet publish $Root\native\acadsharp-dump\ACadSharpDump.csproj -c Release"
} else {
  Write-Host "dotnet not found. DXF-only mode works; install .NET 8 SDK for direct DWG parsing."
}
