# Local-only PowerShell entrypoint. No remote code downloads or execution.
$ErrorActionPreference = 'Stop'
$project = Resolve-Path (Join-Path $PSScriptRoot '..')
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
if (-not $python) { Write-Error 'Python 3 is required. Install Python first via an official source.'; exit 2 }
$entry = Join-Path $project 'cus.py'
if ($python.Name -eq 'py.exe' -or $python.Name -eq 'py') {
  & $python.Source -3 $entry @args
} else {
  & $python.Source $entry @args
}
exit $LASTEXITCODE
