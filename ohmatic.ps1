param(
  [string]$Area = "help",
  [string]$Action = "help",
  [switch]$Server,
  [switch]$Foreground,
  [string]$HostName = "127.0.0.1",
  [int]$Port = 5173
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontend = Join-Path $root "frontend"

function Show-Usage {
  Write-Host "Usage:"
  Write-Host "  /ohmatic frontend start"
  Write-Host "  .\ohmatic.cmd frontend start"
  Write-Host ""
  Write-Host "Default: mock mode, http://127.0.0.1:5173"
  Write-Host "Server:  .\ohmatic.cmd frontend start -Server"
  Write-Host "Logs:    .\ohmatic.cmd frontend start -Foreground"
}

function Test-PortFree([string]$Address, [int]$CandidatePort) {
  $ip = [System.Net.IPAddress]::Loopback
  if (-not [System.Net.IPAddress]::TryParse($Address, [ref]$ip)) {
    $ip = [System.Net.IPAddress]::Loopback
  }
  $listener = [System.Net.Sockets.TcpListener]::new($ip, $CandidatePort)
  try {
    $listener.Start()
    return $true
  } catch {
    return $false
  } finally {
    $listener.Stop()
  }
}

function Find-Port([string]$Address, [int]$StartPort) {
  for ($candidate = $StartPort; $candidate -lt ($StartPort + 20); $candidate++) {
    if (Test-PortFree $Address $candidate) {
      return $candidate
    }
  }
  throw "No free frontend port found from $StartPort to $($StartPort + 19)."
}

function Start-DetachedFrontend([string]$Address, [int]$SelectedPort, [bool]$UseServer) {
  $log = Join-Path $frontend "ohmatic-frontend.log"
  $modePrefix = if ($UseServer) { "set VITE_OHMATIC_USE_MOCK=&" } else { "set VITE_OHMATIC_USE_MOCK=1&" }
  $command = "$modePrefix npm.cmd run dev -- --host $Address --port $SelectedPort > `"$log`" 2>&1"

  $info = [System.Diagnostics.ProcessStartInfo]::new()
  $info.FileName = "cmd.exe"
  $info.Arguments = "/d /c `"$command`""
  $info.WorkingDirectory = $frontend
  $info.UseShellExecute = $false
  $info.CreateNoWindow = $true

  $process = [System.Diagnostics.Process]::Start($info)
  Start-Sleep -Milliseconds 900
  return @{ Process = $process; Log = $log }
}

if ($Area -eq "help" -and $Action -eq "help") {
  Show-Usage
  exit 0
}

if ($Area -ne "frontend" -or $Action -ne "start") {
  Show-Usage
  exit 2
}

if (-not (Test-Path -LiteralPath (Join-Path $frontend "package.json"))) {
  throw "frontend/package.json not found from $root"
}

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
  throw "npm.cmd was not found on PATH. Install Node.js or use the bundled project environment."
}

Push-Location $frontend
try {
  if (-not (Test-Path -LiteralPath "node_modules")) {
    Write-Host "Installing frontend dependencies..."
    & npm.cmd install
    if ($LASTEXITCODE -ne 0) {
      exit $LASTEXITCODE
    }
  }

  if (-not (Test-PortFree $HostName $Port)) {
    Write-Host "Ohmatic frontend already has a listener on http://$HostName`:$Port"
    exit 0
  }

  $selectedPort = Find-Port $HostName $Port
  if ($Server) {
    Remove-Item Env:VITE_OHMATIC_USE_MOCK -ErrorAction SilentlyContinue
    Write-Host "Ohmatic frontend: server mode"
  } else {
    $env:VITE_OHMATIC_USE_MOCK = "1"
    Write-Host "Ohmatic frontend: mock mode"
  }

  Write-Host "Open: http://$HostName`:$selectedPort"
  if ($Foreground) {
    & npm.cmd run dev -- --host $HostName --port $selectedPort
    exit $LASTEXITCODE
  }

  $started = Start-DetachedFrontend $HostName $selectedPort $Server.IsPresent
  Write-Host "PID: $($started.Process.Id)"
  Write-Host "Log: $($started.Log)"
  exit 0
} finally {
  Pop-Location
}
