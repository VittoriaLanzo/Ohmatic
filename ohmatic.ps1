#requires -Version 5.1
<#
  ohmatic - one-command local launcher.

  Usage:
    ohmatic start            Boot the full stack: Python backend stubs + frontend (server mode).
    ohmatic start -Mock      Frontend only, mock mode (no backend).
    ohmatic start -Docker    Use docker compose for the backend instead of Python stubs.
    ohmatic stop             Stop everything ohmatic started.
    ohmatic status           Show what is currently running.
    ohmatic doctor           Diagnose the system (Node, Python, Docker, ports).
    ohmatic help             Show this help.

  Dead-simple path after a fresh clone:
    ohmatic start            -> open the printed http://127.0.0.1:<port> URL.

  Requires: Node.js + npm (frontend), Python 3 (backend stubs). Docker only for -Docker.
#>
param(
  [Parameter(Position = 0)][string]$Command = "help",
  [Parameter(Position = 1)][string]$Subcommand = "",
  [switch]$Mock,
  [switch]$Docker,
  [switch]$Foreground,
  [string]$HostName = "127.0.0.1",
  [int]$Port = 5173
)

$ErrorActionPreference = "Stop"

# Circuit glyphs are built from code points, not pasted into the source: PS 5.1
# may read this file as ANSI, which would mangle raw box-drawing into mojibake.
# Pushing the console to UTF-8 lets the pads and traces render instead of '?'.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$Glyph = @{
  Step  = [char]0x25B8   # signal entering a stage
  Pad   = [char]0x25CF   # lit pad / exit 0
  Warn  = [char]0x25B2   # amber flag
  Fail  = [char]0x2715   # blown pad
  Skip  = [char]0x00B7   # not energised
  Trace = [char]0x2501   # the rail
  Omega = [char]0x03A9   # the mark
  Arrow = [char]0x2192   # before -> after
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontend = Join-Path $root "frontend"
$runDir = Join-Path $root ".ohmatic-run"

# Backend services: name, working dir (holds server.py), and the port it binds.
# The frontend only needs the gateway on :8080; the others mirror the real topology.
$Services = @(
  @{ Name = "gateway";   Dir = (Join-Path $root "gateway/stub");   Port = 8080 },
  @{ Name = "inference"; Dir = (Join-Path $root "inference/stub"); Port = 8001 },
  @{ Name = "verifier";  Dir = (Join-Path $root "verifier/stub");  Port = 8002 }
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

function Write-Step([string]$Message) { Write-Host "$($Glyph.Step) $Message" -ForegroundColor Cyan }
function Write-Ok([string]$Message)   { Write-Host "  $($Glyph.Pad)  $Message" -ForegroundColor Green }
function Write-Warn2([string]$Message) { Write-Host "  $($Glyph.Warn)  $Message" -ForegroundColor Yellow }
function Write-Fail([string]$Message)  { Write-Host "  $($Glyph.Fail)  $Message" -ForegroundColor Red }
function Write-Dim([string]$Message)   { Write-Host "  $($Glyph.Skip)  $Message" -ForegroundColor DarkGray }

# The masthead is the product pipeline drawn as a PCB trace: lit pads at each
# stage, signal flowing left to right. Same Normalize/Generate/Verify/Deliver
# rail the frontend lights up while a job runs.
function Show-Banner {
  $seg = [string]$Glyph.Trace * 2
  Write-Host ""
  Write-Host "  $($Glyph.Omega) " -ForegroundColor Green -NoNewline
  Write-Host "ohmatic" -ForegroundColor White -NoNewline
  Write-Host "    a compiler for circuits" -ForegroundColor DarkGray
  Write-Host "  " -NoNewline
  Write-Host $Glyph.Pad -ForegroundColor Green -NoNewline
  foreach ($station in @("normalize", "generate", "verify", "deliver")) {
    Write-Host "$seg $station $seg" -ForegroundColor Gray -NoNewline
    Write-Host $Glyph.Pad -ForegroundColor Green -NoNewline
  }
  Write-Host " $($Glyph.Step)" -ForegroundColor Green
  Write-Host ""
}

function Show-Usage {
  Show-Banner
  Write-Host "  ohmatic start          Full stack: Python backend stubs + frontend (server mode)"
  Write-Host "  ohmatic start -Mock    Frontend only, mock mode (no backend)"
  Write-Host "  ohmatic start -Docker  Backend via docker compose instead of Python stubs"
  Write-Host "  ohmatic stop           Stop everything ohmatic started"
  Write-Host "  ohmatic status         Show what is running"
  Write-Host "  ohmatic doctor         Diagnose the system (Node, Python, Docker, ports, RAM/GPU -> tier)"
  Write-Host "  ohmatic onboarding     Scan hardware + install the matching model (auto on first start)"
  Write-Host "  ohmatic fetch [tier]   Download weights (recommended tier, or bf16 / q8_0 / q4_k_m)"
  Write-Host "  ohmatic update         Reset this clone to the latest GitHub main (discards local edits)"
  Write-Host "  ohmatic help           Show this help"
  Write-Host ""
  Write-Host "  Fresh clone -> 'ohmatic start' -> open the printed URL." -ForegroundColor DarkGray
}

function Test-PythonWorks([string]$Exe, [string[]]$Pre) {
  # A python on PATH is not necessarily usable: a broken install (missing Lib)
  # still resolves but cannot import its own stdlib. Probe before trusting it.
  try {
    & $Exe @Pre "-c" "import sys" *> $null
    return ($LASTEXITCODE -eq 0)
  } catch {
    return $false
  }
}

function Get-PythonCmd {
  $candidates = New-Object System.Collections.ArrayList

  foreach ($name in @("python", "python3")) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { [void]$candidates.Add(@{ File = $cmd.Source; PreArgs = @() }) }
  }
  $py = Get-Command "py" -ErrorAction SilentlyContinue
  if ($py) { [void]$candidates.Add(@{ File = $py.Source; PreArgs = @("-3") }) }

  # Common install locations, in case PATH only exposes a broken interpreter.
  $globs = @(
    (Join-Path $env:USERPROFILE "anaconda3\python.exe"),
    (Join-Path $env:USERPROFILE "miniconda3\python.exe"),
    (Join-Path $env:USERPROFILE "AppData\Local\Programs\Python\Python3*\python.exe"),
    (Join-Path $env:LOCALAPPDATA  "Programs\Python\Python3*\python.exe")
  )
  foreach ($pattern in $globs) {
    Get-ChildItem -Path $pattern -ErrorAction SilentlyContinue | ForEach-Object {
      [void]$candidates.Add(@{ File = $_.FullName; PreArgs = @() })
    }
  }

  foreach ($candidate in $candidates) {
    if (Test-PythonWorks $candidate.File $candidate.PreArgs) { return $candidate }
  }
  return $null
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
    if (Test-PortFree $Address $candidate) { return $candidate }
  }
  throw "No free port found from $StartPort to $($StartPort + 19)."
}

function Test-HttpOk([string]$Url) {
  try {
    $resp = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
    return ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500)
  } catch {
    return $false
  }
}

function Save-Pid([string]$Name, [int]$ProcessId) {
  if (-not (Test-Path -LiteralPath $runDir)) {
    New-Item -ItemType Directory -Path $runDir | Out-Null
  }
  Set-Content -LiteralPath (Join-Path $runDir "$Name.pid") -Value $ProcessId -Encoding ascii
}

function Get-PortsFile { Join-Path $runDir "ports.txt" }

function Read-RunPorts {
  $map = @{}
  $pf = Get-PortsFile
  if (Test-Path -LiteralPath $pf) {
    foreach ($line in (Get-Content -LiteralPath $pf -ErrorAction SilentlyContinue)) {
      $parts = $line -split '\s+'
      if ($parts.Count -ge 2 -and ($parts[1] -as [int])) { $map[$parts[0]] = [int]$parts[1] }
    }
  }
  return $map
}

function Add-RunPort([string]$Name, [int]$P) {
  if (-not (Test-Path -LiteralPath $runDir)) { New-Item -ItemType Directory -Path $runDir | Out-Null }
  Add-Content -LiteralPath (Get-PortsFile) -Value "$Name $P" -Encoding ascii
}

function Stop-ByPidFile([string]$PidFile) {
  $name = [System.IO.Path]::GetFileNameWithoutExtension($PidFile)
  $processId = (Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
  if ($processId -and ($processId -as [int])) {
    if (Get-Process -Id $processId -ErrorAction SilentlyContinue) {
      # taskkill /T tears down the child tree (vite spawns esbuild, etc.).
      & taskkill.exe /PID $processId /T /F 2>&1 | Out-Null
      Write-Ok "stopped $name (pid $processId)"
    } else {
      Write-Warn2 "$name (pid $processId) was not running"
    }
  }
  Remove-Item -LiteralPath $PidFile -ErrorAction SilentlyContinue
}

function Start-DetachedProcess([string]$File, [string[]]$ArgList, [string]$WorkDir, [string]$LogPath) {
  # File redirection happens at the OS level, so the child keeps writing to the log
  # even after this launcher process exits. stdout and stderr cannot share one file.
  $errPath = [System.IO.Path]::ChangeExtension($LogPath, ".err.log")
  $startArgs = @{
    FilePath               = $File
    ArgumentList           = $ArgList
    WorkingDirectory       = $WorkDir
    WindowStyle            = "Hidden"
    PassThru               = $true
    RedirectStandardOutput = $LogPath
    RedirectStandardError  = $errPath
  }
  return Start-Process @startArgs
}

# ---------------------------------------------------------------------------
# backend
# ---------------------------------------------------------------------------

# Returns the gateway's chosen port (the only one the frontend needs to reach).
function Start-BackendStubs {
  $python = Get-PythonCmd
  if (-not $python) {
    throw "Python 3 not found on PATH. Install Python 3 or use 'ohmatic start -Docker'."
  }
  if (-not (Test-Path -LiteralPath $runDir)) { New-Item -ItemType Directory -Path $runDir | Out-Null }
  Remove-Item -LiteralPath (Get-PortsFile) -ErrorAction SilentlyContinue

  $gatewayPort = 8080
  foreach ($svc in $Services) {
    $serverPy = Join-Path $svc.Dir "server.py"
    if (-not (Test-Path -LiteralPath $serverPy)) {
      Write-Warn2 "$($svc.Name): server.py missing, skipped"
      continue
    }
    # Each service binds a free port; nothing is hardcoded, so busy machines just work.
    $chosen = Find-Port $HostName $svc.Port
    $log = Join-Path $runDir "$($svc.Name).log"
    $argList = @($python.PreArgs + @("server.py"))
    $env:OHMATIC_PORT = "$chosen"
    $process = Start-DetachedProcess $python.File $argList $svc.Dir $log
    Remove-Item Env:OHMATIC_PORT -ErrorAction SilentlyContinue
    Save-Pid $svc.Name $process.Id
    Add-RunPort $svc.Name $chosen
    if ($svc.Name -eq "gateway") { $gatewayPort = $chosen }
    Write-Ok "$($svc.Name) -> http://$HostName`:$chosen  (pid $($process.Id))"
  }
  # The gateway is confirmed by the health gate below; the other stubs surface in 'status'.
  return $gatewayPort
}

function Start-BackendDocker {
  if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "docker not found on PATH. Drop -Docker to use the Python stub backend."
  }
  Write-Step "Starting backend via docker compose"
  Push-Location $root
  try {
    & docker compose up -d
    if ($LASTEXITCODE -ne 0) { throw "docker compose up failed (exit $LASTEXITCODE)." }
  } finally {
    Pop-Location
  }
}

function Wait-ForGateway([int]$GatewayPort = 8080) {
  $url = "http://$HostName`:$GatewayPort/health"
  Write-Step "Waiting for gateway $url"
  for ($i = 0; $i -lt 30; $i++) {
    if (Test-HttpOk $url) { Write-Ok "gateway healthy"; return $true }
    Start-Sleep -Milliseconds 500
  }
  Write-Warn2 "gateway did not answer /health in time (check .ohmatic-run\gateway.log)"
  return $false
}

# ---------------------------------------------------------------------------
# frontend
# ---------------------------------------------------------------------------

function Ensure-FrontendDeps {
  if (-not (Test-Path -LiteralPath (Join-Path $frontend "package.json"))) {
    throw "frontend/package.json not found under $root"
  }
  if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue) -and -not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm not found on PATH. Install Node.js (https://nodejs.org)."
  }
  if (-not (Test-Path -LiteralPath (Join-Path $frontend "node_modules"))) {
    Write-Step "Installing frontend dependencies (first run)"
    Push-Location $frontend
    try {
      & npm install
      if ($LASTEXITCODE -ne 0) { throw "npm install failed (exit $LASTEXITCODE)." }
    } finally {
      Pop-Location
    }
  }
}

function Start-Frontend([bool]$UseMock) {
  Ensure-FrontendDeps
  if (-not (Test-PortFree $HostName $Port)) {
    $existing = $Port
    $Port = Find-Port $HostName ($Port + 1)
    Write-Warn2 "port $existing busy, using $Port"
  } else {
    $Port = Find-Port $HostName $Port
  }

  if ($UseMock) {
    $env:VITE_OHMATIC_USE_MOCK = "1"
    Write-Step "Frontend: mock mode"
  } else {
    Remove-Item Env:VITE_OHMATIC_USE_MOCK -ErrorAction SilentlyContinue
    $gw = if ($env:OHMATIC_GATEWAY_URL) { $env:OHMATIC_GATEWAY_URL } else { "http://$HostName`:8080" }
    Write-Step "Frontend: server mode (proxying /v1 + /health -> $gw)"
  }

  $url = "http://$HostName`:$Port"
  if ($Foreground) {
    Push-Location $frontend
    try { & npm run dev -- --host $HostName --port $Port } finally { Pop-Location }
    return $url
  }

  $npmCmd = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
  if (-not $npmCmd) { $npmCmd = (Get-Command npm).Source }
  $log = Join-Path $runDir "frontend.log"
  if (-not (Test-Path -LiteralPath $runDir)) { New-Item -ItemType Directory -Path $runDir | Out-Null }
  $argList = @("run", "dev", "--", "--host", $HostName, "--port", "$Port")
  $process = Start-DetachedProcess $npmCmd $argList $frontend $log
  Save-Pid "frontend" $process.Id
  Write-Ok "frontend -> $url  (pid $($process.Id))"
  return $url
}

# ---------------------------------------------------------------------------
# hardware assessment + first-run model onboarding
# ---------------------------------------------------------------------------

# RAM + NVIDIA VRAM -> which Ohmatic model this machine can run. Writes
# .ohmatic-run\doctor.json (the same schema the gateway and the bash launcher use).
# Every probe is guarded: a missing nvidia-smi or locked-down WMI just degrades the
# verdict to a lower tier - it never throws and never blocks the launcher.
function Get-HwAssess {
  if (-not (Test-Path -LiteralPath $runDir)) { New-Item -ItemType Directory -Path $runDir | Out-Null }
  $ramGb = 0; $vramMb = 0; $gpu = ""
  try { $ramGb = [int][math]::Floor([double]((Get-CimInstance Win32_ComputerSystem -ErrorAction Stop).TotalPhysicalMemory) / 1GB) } catch { $ramGb = 0 }
  if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    try {
      $vramMb = [int]((& nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>$null | Select-Object -First 1).ToString().Trim())
      $gpu    = ((& nvidia-smi --query-gpu=name --format=csv,noheader 2>$null | Select-Object -First 1).ToString().Trim())
    } catch { $vramMb = 0; $gpu = "" }
  }
  $tier = "stub"; $why = "not enough RAM/VRAM for local inference - stub/cloud mode"
  if     ($vramMb -ge 20000) { $tier = "bf16";       $why = "$gpu ($vramMb MB VRAM) fits the full bf16 model" }
  elseif ($vramMb -ge 10000) { $tier = "q8_0";       $why = "$gpu ($vramMb MB VRAM) fits the Q8_0 GGUF" }
  elseif ($vramMb -ge 6000)  { $tier = "q4_k_m";     $why = "$gpu ($vramMb MB VRAM) fits the Q4_K_M GGUF" }
  # Q4_K_M CPU floor = 11 GB: _ram_guard's committed peak (weights + KV + prefix cache)
  # plus a ~2 GB OS reserve; T5 is subprocess-isolated and no longer counted. Keep in
  # sync with gateway/stub/server.py so the doctor never recommends a tier the guard refuses.
  elseif ($ramGb  -ge 11)    { $tier = "q4_k_m_cpu"; $why = "$ramGb GB RAM runs the Q4_K_M GGUF on CPU (slower)" }
  $checkedAt = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
  $payload = [ordered]@{ ram_gb = $ramGb; vram_mb = $vramMb; gpu = $gpu; recommended_model = $tier; reason = $why; checked_at = $checkedAt }
  ($payload | ConvertTo-Json -Compress) | Set-Content -LiteralPath (Join-Path $runDir "doctor.json") -Encoding utf8
  return [pscustomobject]@{ Tier = $tier; Why = $why; RamGb = $ramGb; VramMb = $vramMb; Gpu = $gpu }
}

# Approx on-disk size per tier (model + the ~1 GB T5 normalizer pulled alongside).
# Drives the progress bar and the size hint only.
$script:TierGb = @{ bf16 = 17.5; q8_0 = 10.0; q4_k_m = 6.0; q4_k_m_cpu = 6.0 }

# Download the weights for $Tier anonymously (the repos are public - no token, no
# login) and render one determinate progress bar from the models\ directory growth.
# The HF downloader is authoritative; the bar is best-effort so a polling hiccup
# never fails the install. Returns $true on success.
function Install-Model([string]$Tier) {
  $python = Get-PythonCmd
  if (-not $python) { Write-Fail "Python 3 not found - cannot download weights. Install Python 3, then 'ohmatic onboarding'."; return $false }
  $modelsDir = Join-Path $root "models"
  if (-not (Test-Path -LiteralPath $modelsDir)) { New-Item -ItemType Directory -Path $modelsDir | Out-Null }
  $baseBytes = [double]((Get-ChildItem -LiteralPath $modelsDir -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum)
  $expectGb = $script:TierGb[$Tier]; if (-not $expectGb) { $expectGb = 6.0 }
  $total = [double]$expectGb * 1GB
  Write-Step "Installing the '$Tier' model (~$([int]$expectGb) GB, one time)..."
  $log = Join-Path $runDir "fetch.log"
  $argList = @($python.PreArgs + @("tools/fetch_model.py", "--tier", $Tier))
  $proc = Start-Process -FilePath $python.File -ArgumentList $argList -WorkingDirectory $root -PassThru -NoNewWindow `
            -RedirectStandardOutput $log -RedirectStandardError ([System.IO.Path]::ChangeExtension($log, ".err.log"))
  while (-not $proc.HasExited) {
    Start-Sleep -Milliseconds 700
    $cur = [double]((Get-ChildItem -LiteralPath $modelsDir -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum)
    $dl  = [math]::Max(0, $cur - $baseBytes)
    $pct = [math]::Min(99, [int](($dl / $total) * 100))
    Write-Progress -Activity "Installing '$Tier' model" -Status ("{0:N1} of ~{1:N0} GB" -f ($dl / 1GB), $expectGb) -PercentComplete $pct
  }
  Write-Progress -Activity "Installing '$Tier' model" -Completed
  if ($proc.ExitCode -ne 0) {
    Write-Fail "download failed (exit $($proc.ExitCode)). See $log"
    return $false
  }
  Write-Ok "model installed -> models\active.json"
  return $true
}

# First-run consumer onboarding: scan the machine, suggest the matching model, one
# keypress to install. Skips if a model is already present; skips the prompt in
# non-interactive shells (CI). Safe to run standalone: 'ohmatic onboarding'.
function Invoke-Onboarding {
  $hw = Get-HwAssess
  $active = Join-Path $root "models\active.json"
  if (Test-Path -LiteralPath $active) {
    $tierInstalled = $null
    try { $tierInstalled = (Get-Content -Raw -LiteralPath $active | ConvertFrom-Json).tier } catch { }
    $suffix = if ($tierInstalled) { " (tier '$tierInstalled')" } else { "" }
    Write-Ok "A local model is already installed$suffix. Skipping download."
    return
  }
  $vramPart = if ($hw.VramMb -gt 0) { " and $($hw.VramMb) MB VRAM ($($hw.Gpu))" } else { "" }
  Write-Host ""
  Write-Host "  Ohmatic doctor scanned your device and found $($hw.RamGb) GB RAM$vramPart." -ForegroundColor White
  if ($hw.Tier -eq "stub") {
    Write-Warn2 "Not enough memory for a local model - Ohmatic runs in stub mode. You can still explore the full loop."
    return
  }
  $sizeGb = [int]$script:TierGb[$hw.Tier]
  Write-Host "  I suggest you install the '$($hw.Tier)' model (~$sizeGb GB, generator + T5 normalizer) - $($hw.Why)." -ForegroundColor White
  if ([Console]::IsInputRedirected) { Write-Dim "non-interactive shell - run 'ohmatic onboarding' to install when ready"; return }
  $ans = Read-Host "  Want to go ahead? [Y/N]"
  if ($ans -match '^\s*(y|yes|)\s*$') {
    [void](Install-Model $hw.Tier)
  } else {
    Write-Dim "skipped - run 'ohmatic onboarding' (or 'ohmatic fetch') whenever you want the model"
  }
}

# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

function Invoke-Fetch {
  $hw = Get-HwAssess
  $tier = if ($Subcommand -and $Subcommand -ne "all") { $Subcommand } else { $hw.Tier }
  Write-Step "Ohmatic fetch"
  Write-Dim "tier $tier ($($hw.Why))"
  [void](Install-Model $tier)
}

function Invoke-Start {
  Show-Banner
  Write-Step "Ohmatic starting"
  # First run: scan hardware, offer the matching model, then auto-open the app at
  # the end. The marker lives in the ephemeral run dir so a fresh clone re-onboards.
  $onboardMarker = Join-Path $runDir ".onboarded"
  $firstRun = -not (Test-Path -LiteralPath $onboardMarker)
  if ($firstRun -and -not $Mock) {
    Invoke-Onboarding
    if (-not (Test-Path -LiteralPath $runDir)) { New-Item -ItemType Directory -Path $runDir | Out-Null }
    Set-Content -LiteralPath $onboardMarker -Value ([DateTime]::UtcNow.ToString("o")) -Encoding ascii
  }
  $gatewayPort = 8080
  if (-not $Mock) {
    if ($Docker) {
      Start-BackendDocker
    } else {
      Write-Step "Starting Python backend stubs"
      $gatewayPort = Start-BackendStubs
    }
    Wait-ForGateway $gatewayPort | Out-Null
    # Point the dev-server proxy at the gateway's actual port; the browser stays same-origin.
    $env:OHMATIC_GATEWAY_URL = "http://$HostName`:$gatewayPort"
  } else {
    Write-Warn2 "mock mode: backend not started"
  }
  $url = Start-Frontend ([bool]$Mock)
  Write-Host ""
  Write-Host "Ohmatic is up:" -ForegroundColor White
  Write-Host "  Frontend : $url" -ForegroundColor Green
  if (-not $Mock) { Write-Host "  Gateway  : http://$HostName`:$gatewayPort" -ForegroundColor Green }
  Write-Host "  Stop     : ohmatic stop" -ForegroundColor DarkGray
  Write-Host "  Logs     : .ohmatic-run\*.log" -ForegroundColor DarkGray
  # First run opens the app for you; later starts just print the URL.
  if ($firstRun -and -not [Console]::IsInputRedirected) {
    Write-Step "Opening Ohmatic in your browser"
    try { Start-Process $url } catch { Write-Dim "open $url manually" }
  }
  Write-Host ""
  Write-Host "  Compiles clean, or it doesn't ship." -ForegroundColor DarkGray
}

function Invoke-Stop {
  Write-Step "Stopping ohmatic"
  if (Test-Path -LiteralPath $runDir) {
    Get-ChildItem -LiteralPath $runDir -Filter "*.pid" -ErrorAction SilentlyContinue | ForEach-Object {
      Stop-ByPidFile $_.FullName
    }
    Remove-Item -LiteralPath (Get-PortsFile) -ErrorAction SilentlyContinue
  }
  if ($Docker -or (Get-Command docker -ErrorAction SilentlyContinue)) {
    Push-Location $root
    try { & docker compose down *> $null } catch { } finally { Pop-Location }
  }
  Write-Ok "done"
}

function Invoke-Doctor {
  Write-Step "Ohmatic doctor"
  $okFrontend = $true
  $okBackend = $false

  # --- OS / shell ---
  Write-Dim "os        Windows ($([System.Environment]::OSVersion.Version)), PowerShell $($PSVersionTable.PSVersion)"

  # --- Node + npm (required for the frontend) ---
  $node = Get-Command node -ErrorAction SilentlyContinue
  if ($node) {
    $nodeVer = (& $node.Source --version) 2>$null
    Write-Ok "node      $nodeVer  ($($node.Source))"
  } else {
    Write-Fail "node      not found - install Node.js 18+ (https://nodejs.org)"
    $okFrontend = $false
  }
  $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
  if (-not $npm) { $npm = Get-Command npm -ErrorAction SilentlyContinue }
  if ($npm) {
    $npmVer = (& $npm.Source --version) 2>$null
    Write-Ok "npm       $npmVer"
  } else {
    Write-Fail "npm       not found - ships with Node.js"
    $okFrontend = $false
  }

  # --- Python (default backend) ---
  $python = Get-PythonCmd
  if ($python) {
    $pyVer = (& $python.File @($python.PreArgs) "-c" "import sys;print(sys.version.split()[0])") 2>$null
    Write-Ok "python    $pyVer  ($($python.File) $($python.PreArgs -join ' '))"
    $okBackend = $true
  } else {
    Write-Warn2 "python    no working interpreter found (broken or missing) - backend needs Python 3 or Docker"
  }

  # --- Docker (alternative backend) ---
  $docker = Get-Command docker -ErrorAction SilentlyContinue
  if ($docker) {
    $dockerVer = (& $docker.Source --version) 2>$null
    Write-Ok "docker    $dockerVer  (enables: ohmatic start -Docker)"
    $okBackend = $true
  } else {
    Write-Dim "docker    not found (optional - only needed for -Docker)"
  }

  # --- Ports ---
  $ports = @(8080, 8001, 8002, $Port)
  $busy = @()
  foreach ($p in $ports) { if (-not (Test-PortFree $HostName $p)) { $busy += $p } }
  if ($busy.Count -eq 0) { Write-Ok "ports     $($ports -join ', ') all free" }
  else { Write-Warn2 "ports     in use: $($busy -join ', ') (ohmatic will auto-pick the next free frontend port)" }

  # --- Hardware -> model tier (read-only here; install lives in 'ohmatic onboarding') ---
  $hw = Get-HwAssess
  if ($hw.VramMb -gt 0) { Write-Ok "gpu       $($hw.Gpu) ($($hw.VramMb) MB VRAM)" } else { Write-Dim "gpu       no NVIDIA GPU detected" }
  Write-Ok "ram       $($hw.RamGb) GB"
  Write-Ok "model     recommended: $($hw.Tier) - $($hw.Why)"

  # --- Verdict ---
  Write-Host ""
  if ($okFrontend -and $okBackend) {
    Write-Host "Verdict: ready. Run 'ohmatic start'." -ForegroundColor Green
  } elseif ($okFrontend) {
    Write-Host "Verdict: frontend OK but no backend runtime. Run 'ohmatic start -Mock', or install Python 3 / Docker." -ForegroundColor Yellow
  } else {
    Write-Host "Verdict: install Node.js first, then re-run 'ohmatic doctor'." -ForegroundColor Red
  }
}

function Invoke-Status {
  Write-Step "Ohmatic status"
  $ports = Read-RunPorts
  foreach ($svc in $Services) {
    $p = if ($ports.ContainsKey($svc.Name)) { $ports[$svc.Name] } else { $svc.Port }
    $ok = Test-HttpOk "http://$HostName`:$p/health"
    if ($ok) { Write-Ok "$($svc.Name.PadRight(10)) listening on :$p" }
    else { Write-Dim "$($svc.Name.PadRight(10)) not running (:$p)" }
  }
  $fePid = Join-Path $runDir "frontend.pid"
  if (Test-Path -LiteralPath $fePid) {
    $processId = Get-Content -LiteralPath $fePid | Select-Object -First 1
    if ($processId -and (Get-Process -Id $processId -ErrorAction SilentlyContinue)) {
      Write-Ok "frontend    running (pid $processId)"
    } else {
      Write-Dim "frontend    not running"
    }
  } else {
    Write-Dim "frontend    not running"
  }
}

function Invoke-Update {
  Write-Step "Ohmatic update: syncing this clone to the latest GitHub main"
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Fail "git not found on PATH. Install Git, then re-run 'ohmatic update'."
    exit 1
  }

  & git -C $root rev-parse --git-dir 2>$null | Out-Null
  if ($LASTEXITCODE -ne 0) {
    Write-Fail "not a git checkout. Use 'git clone' so update has a remote to sync from."
    exit 1
  }

  # Hard reset to origin/main: this clone tracks the published main, not your
  # working copy. Local commits and tracked edits are discarded (untracked
  # files survive). Built for a consumer clone, not a dev checkout with WIP.
  & git -C $root diff --quiet 2>$null
  $dirtyTree = ($LASTEXITCODE -ne 0)
  & git -C $root diff --cached --quiet 2>$null
  $dirtyIndex = ($LASTEXITCODE -ne 0)
  if ($dirtyTree -or $dirtyIndex) { Write-Warn2 "local changes will be discarded (hard reset to origin/main)" }

  & git -C $root fetch origin
  if ($LASTEXITCODE -ne 0) { Write-Fail "fetch failed: check the network or the remote."; exit 1 }

  $before = (& git -C $root rev-parse --short HEAD 2>$null)
  & git -C $root reset --hard origin/main
  if ($LASTEXITCODE -ne 0) {
    Write-Fail "reset failed: is 'main' on origin? Check 'git status'."
    exit 1
  }
  $after = (& git -C $root rev-parse --short HEAD 2>$null)

  if ($before -eq $after) {
    Write-Ok "already current at $after"
  } else {
    Write-Ok "reset $before $($Glyph.Arrow) $after (origin/main)"
    # Reinstall only when the reset actually moved package.json; otherwise a no-op.
    $changed = (& git -C $root diff --name-only $before $after 2>$null)
    if ($changed -match "frontend/package\.json") {
      Write-Step "frontend dependencies changed: reinstalling"
      $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
      if (-not $npm) { $npm = Get-Command npm -ErrorAction SilentlyContinue }
      if ($npm) {
        Push-Location $frontend
        try { & $npm.Source install } finally { Pop-Location }
      } else {
        Write-Warn2 "npm not found: run 'npm install' in frontend/ before the next start"
      }
    }
  }
  Write-Ok "done. Restart with: ohmatic stop ; ohmatic start"
}

# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

switch ($Command.ToLowerInvariant()) {
  "start" {
    # Legacy: 'ohmatic frontend start' == mock frontend only.
    if ($Subcommand -eq "" -or $Subcommand.ToLowerInvariant() -eq "all") { Invoke-Start }
    else { Show-Usage; exit 2 }
  }
  "frontend" {
    if ($Subcommand.ToLowerInvariant() -eq "start") { $script:Mock = $true; Invoke-Start }
    else { Show-Usage; exit 2 }
  }
  "stop"   { Invoke-Stop }
  "status" { Invoke-Status }
  "doctor" { Invoke-Doctor }
  "onboarding" { Show-Banner; Invoke-Onboarding }
  "fetch"  { Invoke-Fetch }
  "update" { Invoke-Update }
  "help"   { Show-Usage }
  default  { Show-Usage; exit 2 }
}
