# Starts Jarvis in the background via its supervisor (auto-restart, low priority).
#   start-hidden.ps1        -> background only (Windows logon; Jarvis greets you)
#   start-hidden.ps1 -App   -> also open the Jarvis window
param([switch]$App)
$ErrorActionPreference = 'SilentlyContinue'
$root = $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\pythonw.exe'

$running = $false
try { $running = (Invoke-WebRequest -Uri 'http://127.0.0.1:50778/api/state' -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch {}
if ($running) {
    if ($App) { Start-Process $py -ArgumentList "`"$root\assistant.py`"", '--app' -WorkingDirectory $root }
    exit
}
$args = @("`"$root\supervisor.py`"")
if ($App) { $args += '--app' }
Start-Process -FilePath $py -ArgumentList $args -WorkingDirectory $root
