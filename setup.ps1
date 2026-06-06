# =============================================================================
#  TMRP one-click demo installer (Windows)
# -----------------------------------------------------------------------------
#  Brings up the full TMRP stack on a clean Windows machine that has nothing
#  installed. It runs in two phases because enabling the WSL2 platform requires
#  a reboot:
#
#    Phase 1 (this run)  : enable WSL + VirtualMachinePlatform, schedule a
#                          resume task, then reboot.
#    Phase 2 (after login): install Docker Desktop, generate the .env files and
#                          Docker secrets, build + start the stack, open the
#                          browser, and print the admin login.
#
#  The professor double-clicks setup.bat ONCE, approves the single UAC prompt,
#  lets the machine reboot itself, and the browser opens automatically when the
#  stack is healthy. Run teardown.bat afterwards to remove everything.
#
#  All file/secret generation happens locally and is gitignored, consistent
#  with the project's "secrets never enter git" design.
# =============================================================================

param([switch]$Resume)

$ErrorActionPreference = 'Stop'
# Windows PowerShell 5.1 renders a per-chunk progress bar for Invoke-WebRequest
# that makes large (~1 GB) downloads many times slower. Suppress it globally.
$ProgressPreference = 'SilentlyContinue'

# --- paths / constants -------------------------------------------------------
$RepoRoot     = $PSScriptRoot
$StateDir     = Join-Path $env:LOCALAPPDATA 'TMRP-Setup'
$ManifestPath = Join-Path $StateDir 'install-manifest.json'
$TaskName     = 'TMRPSetupResume'
$WebUrl       = 'http://localhost:41080'
# Explicit project name (-p) so `up` and `teardown`'s `down` always target the
# same project. The repo folder name contains spaces/parentheses/non-ASCII, and
# Compose's auto-derived project name from that is unpredictable.
$ComposeArgs  = @('compose', '-p', 'tmrp', '-f', 'docker-compose.yml', '-f', 'docker-compose.run.yml')

$script:Rebooting = $false
$script:HandingOff = $false   # set when this process re-launches itself elevated

# =============================================================================
#  Helpers
# =============================================================================

function Write-Step  { param($m) Write-Host "`n==> $m" -ForegroundColor Cyan }
function Write-Info  { param($m) Write-Host "    $m" -ForegroundColor Gray }
function Write-Ok    { param($m) Write-Host "    $m" -ForegroundColor Green }
function Write-Warn2 { param($m) Write-Host "    $m" -ForegroundColor Yellow }

function Test-Admin {
    $id = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object System.Security.Principal.WindowsPrincipal($id)).IsInRole(
        [System.Security.Principal.WindowsBuiltInRole]::Administrator)
}

# --- cryptographically strong value generators -------------------------------
$script:Rng = [System.Security.Cryptography.RNGCryptoServiceProvider]::new()

function Get-RandomBytes { param([int]$Count)
    $b = New-Object 'byte[]' $Count
    $script:Rng.GetBytes($b)
    ,$b
}

function Get-RandomFromSet { param([string]$Set, [int]$Count)
    $bytes = Get-RandomBytes -Count $Count
    -join ($bytes | ForEach-Object { $Set[$_ % $Set.Length] })
}

# 64 hex chars (32 random bytes) — satisfies JWT_SECRET_KEY >= 32 chars.
function New-HexKey { param([int]$Bytes = 32)
    $b = Get-RandomBytes -Count $Bytes
    ($b | ForEach-Object { $_.ToString('x2') }) -join ''
}

# URL-safe (alphanumeric only) so it can sit in postgresql://user:PASS@host
# without breaking DATABASE_URL parsing in docker-entrypoint.sh.
function New-AlnumPassword {
    Get-RandomFromSet 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789' 28
}

# 20 chars guaranteed to contain all four character classes — required by the
# ADMIN_PASSWORD validator (Settings + docker-entrypoint.sh reject weaker ones).
function New-StrongPassword {
    $lower = 'abcdefghijkmnpqrstuvwxyz'
    $upper = 'ABCDEFGHJKLMNPQRSTUVWXYZ'
    $digit = '23456789'
    $sym   = '!@#%^*-_=+'
    $all   = "$lower$upper$digit$sym"
    $chars = @()
    $chars += Get-RandomFromSet $lower 1
    $chars += Get-RandomFromSet $upper 1
    $chars += Get-RandomFromSet $digit 1
    $chars += Get-RandomFromSet $sym   1
    for ($i = 0; $i -lt 16; $i++) { $chars += Get-RandomFromSet $all 1 }
    # Shuffle so the guaranteed-class chars are not always in the first 4 slots.
    -join ($chars | Sort-Object { Get-Random })
}

# Write UTF-8 without BOM and without a trailing newline — keeps secret files
# clean (docker-entrypoint.sh strips CR/LF anyway, but this avoids surprises).
function Write-TextFile { param($Path, $Content)
    [System.IO.File]::WriteAllText($Path, $Content, (New-Object System.Text.UTF8Encoding($false)))
}

function Get-Manifest {
    # Normalize to a complete object so callers can always read AND assign every
    # field — a partial JSON (e.g. from an older run) would otherwise make
    # property assignment throw under Windows PowerShell 5.1.
    $m = $null
    if (Test-Path $ManifestPath) {
        try { $m = Get-Content $ManifestPath -Raw | ConvertFrom-Json } catch { $m = $null }
    }
    [pscustomobject]@{
        wslEnabledByUs      = [bool]($m.wslEnabledByUs)
        vmpEnabledByUs      = [bool]($m.vmpEnabledByUs)
        dockerInstalledByUs = [bool]($m.dockerInstalledByUs)
        configured          = [bool]($m.configured)
        repoRoot            = if ($m.repoRoot) { $m.repoRoot } else { $RepoRoot }
    }
}

function Save-Manifest { param($m)
    if (-not (Test-Path $StateDir)) { New-Item -ItemType Directory -Path $StateDir -Force | Out-Null }
    ($m | ConvertTo-Json) | Set-Content -Path $ManifestPath -Encoding UTF8
}

function Update-SessionPath {
    $machine = [System.Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user    = [System.Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user"
}

function Get-DockerExe {
    Update-SessionPath
    $cmd = Get-Command docker -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidate = Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe'
    if (Test-Path $candidate) { return $candidate }
    return $null
}

# --- resume-after-reboot scheduled task --------------------------------------
# A scheduled task (RunLevel Highest, at logon) resumes Phase 2 elevated with
# no second UAC prompt. We delete it as soon as Phase 2 starts.

# The task must fire for whoever logs in interactively AFTER the reboot — which
# is not necessarily the identity that elevated this process. If the professor
# is a standard user and approves UAC with a DIFFERENT admin account, then
# $env:USERNAME here is that admin; an AtLogOn task bound to it would never fire
# when the professor logs back into their own account, so Phase 2 would silently
# never resume. We therefore bind the task to the owner of the interactive
# desktop (explorer.exe), falling back to the current user when that lookup
# fails (e.g. explorer not running).
function Get-InteractiveUser {
    try {
        $explorer = Get-CimInstance Win32_Process -Filter "Name='explorer.exe'" -ErrorAction Stop |
                    Select-Object -First 1
        if ($explorer) {
            $owner = Invoke-CimMethod -InputObject $explorer -MethodName GetOwner -ErrorAction Stop
            if ($owner.User) {
                $domain = if ($owner.Domain) { $owner.Domain } else { $env:COMPUTERNAME }
                return "$domain\$($owner.User)"
            }
        }
    } catch { }
    return "$env:USERDOMAIN\$env:USERNAME"
}

function Register-ResumeTask {
    $resumeUser = Get-InteractiveUser
    $ps     = (Get-Command powershell.exe).Source
    $action = New-ScheduledTaskAction -Execute $ps `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Normal -File `"$PSCommandPath`" -Resume"
    $trigger   = New-ScheduledTaskTrigger -AtLogOn -User $resumeUser
    $principal = New-ScheduledTaskPrincipal -UserId $resumeUser `
        -LogonType Interactive -RunLevel Highest
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Principal $principal -Force | Out-Null

    # When the resume user differs from the elevated identity, the seamless
    # "no second prompt" guarantee no longer holds: the task fires for a
    # standard user, Phase 2 re-launches elevated, and one more approval prompt
    # appears. Warn so the professor expects it instead of assuming a failure.
    $current = "$env:USERDOMAIN\$env:USERNAME"
    if ($resumeUser -and ($resumeUser -ne $current)) {
        Write-Warn2 "Setup will resume after reboot for: $resumeUser"
        Write-Warn2 'You may see one more approval prompt when it continues — that is expected.'
    }
}

function Unregister-ResumeTask {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }
}

function Start-CountdownReboot {
    Write-Warn2 'The machine will RESTART in 10 seconds to finish enabling WSL2.'
    Write-Warn2 'Setup resumes automatically after you log back in. Press Ctrl+C to cancel.'
    for ($i = 10; $i -ge 1; $i--) { Write-Host "    restarting in $i ..." ; Start-Sleep -Seconds 1 }
    $script:Rebooting = $true
    Restart-Computer -Force
    exit
}

# =============================================================================
#  Phase 1 — enable WSL2 platform, then reboot
# =============================================================================
function Invoke-Phase1 {
    Write-Step 'Phase 1 / 2 — preparing the Windows virtualization platform'

    # Soft virtualization check. These WMI fields are unreliable across vendors,
    # so we only warn; the real failure surfaces when Docker's engine won't start.
    try {
        $virt = (Get-CimInstance Win32_Processor).VirtualizationFirmwareEnabled
        if ($virt -is [array]) { $virt = $virt[0] }
        if ($virt -eq $false) {
            Write-Warn2 'CPU virtualization appears DISABLED in firmware (BIOS/UEFI).'
            Write-Warn2 'WSL2 and Docker cannot run without it. If setup fails later,'
            Write-Warn2 'enable "Intel VT-x" / "AMD-V" (a.k.a. SVM) in BIOS and retry.'
        }
    } catch { }

    $wsl = (Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux).State
    $vmp = (Get-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform).State

    if ($wsl -eq 'Enabled' -and $vmp -eq 'Enabled') {
        Write-Ok 'WSL2 platform already present — no reboot needed.'
        Invoke-Phase2
        return
    }

    $manifest = Get-Manifest
    $manifest.wslEnabledByUs = ($wsl -ne 'Enabled')
    $manifest.vmpEnabledByUs = ($vmp -ne 'Enabled')
    $manifest.repoRoot       = $RepoRoot
    Save-Manifest $manifest

    Write-Info 'Enabling Windows Subsystem for Linux + Virtual Machine Platform...'
    dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart | Out-Null
    $wslExit = $LASTEXITCODE
    dism.exe /online /enable-feature /featurename:VirtualMachinePlatform          /all /norestart | Out-Null
    $vmpExit = $LASTEXITCODE

    # dism is a native exe: a non-zero exit does NOT throw under
    # ErrorActionPreference=Stop, so a blocked enablement would otherwise pass
    # silently, the machine would reboot, and the real cause would only surface
    # ~6 minutes later as an opaque Docker-engine timeout in Phase 2. Re-query
    # the authoritative feature state and refuse to reboot if either feature is
    # not actually on its way to Enabled. The exit code alone is insufficient
    # (dism returns 3010 — "success, reboot required" — not 0), so we trust the
    # post-condition, not the return value. EnablePending is the expected state
    # after a /norestart enable; Enabled covers the no-reboot-needed case.
    $wslState = (Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux).State
    $vmpState = (Get-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform).State
    $okStates = @('Enabled', 'EnablePending')
    if (($wslState -notin $okStates) -or ($vmpState -notin $okStates)) {
        throw @"
Could not enable the Windows virtualization platform.
  WSL: $wslState (dism exit $wslExit); VirtualMachinePlatform: $vmpState (dism exit $vmpExit)
This usually means the machine is managed by a company/school policy (Group
Policy or MDM) that blocks enabling Windows features. The machine was NOT
rebooted. Run setup on a personally-owned PC, or ask IT to enable
"Windows Subsystem for Linux" and "Virtual Machine Platform", then re-run setup.bat.
"@
    }

    Write-Info 'Scheduling automatic resume after reboot...'
    Register-ResumeTask

    Start-CountdownReboot
}

# =============================================================================
#  Phase 2 — Docker, secrets, and stack launch
# =============================================================================
function Invoke-Phase2 {
    Write-Step 'Phase 2 / 2 — installing Docker and starting TMRP'
    Unregister-ResumeTask

    $manifest = Get-Manifest

    # --- WSL kernel ---
    Write-Info 'Updating the WSL2 kernel (best effort)...'
    try { wsl.exe --update            | Out-Null } catch { Write-Warn2 'wsl --update skipped.' }
    try { wsl.exe --set-default-version 2 | Out-Null } catch { }

    # --- Docker Desktop ---
    if (-not (Get-DockerExe)) {
        Install-DockerDesktop
        $manifest.dockerInstalledByUs = $true
        Save-Manifest $manifest
    } else {
        Write-Ok 'Docker is already installed.'
    }

    $docker = Get-DockerExe
    if (-not $docker) {
        throw 'Docker was installed but its executable could not be located. Please reboot once more and re-run setup.bat.'
    }

    # --- start engine and wait ---
    Write-Step 'Starting the Docker engine (first start can take a minute)'
    Start-DockerDesktop
    if (-not (Wait-DockerEngine -Docker $docker -TimeoutSec 360)) {
        throw @'
Docker engine did not become ready in time. The most common causes are:
  1. CPU virtualization is disabled in BIOS/UEFI (enable Intel VT-x / AMD-V).
  2. Docker Desktop is waiting on its first-run license screen — open it once,
     accept the agreement, then re-run setup.bat.
'@
    }
    Write-Ok 'Docker engine is ready.'

    # --- env + secrets ---
    Write-Step 'Generating local configuration and secrets'
    # Capture this BEFORE New-ProjectConfig flips it. A false value means we are
    # about to generate brand-new secrets — first run, or a run after the
    # manifest was lost (teardown, a disk-cleanup tool, or a DIFFERENT Windows
    # user, since the manifest lives in per-user LOCALAPPDATA while Docker
    # volumes are engine-wide).
    $freshConfig = -not (Get-Manifest).configured
    $creds = New-ProjectConfig

    # When fresh secrets were just generated, drop any leftover data volume from
    # a previous run before starting. Postgres only reads POSTGRES_PASSWORD_FILE
    # when it initializes an EMPTY data dir; a surviving tmrp_pgdata volume would
    # still hold the OLD db password, so the api would fail authentication
    # forever and the web sidecar (depends_on api: healthy) would never start —
    # leaving http://localhost:41080 unreachable with no obvious cause. Dropping
    # it is safe: configured=false means we no longer hold that volume's password
    # anyway, so its data is already unusable.
    if ($freshConfig) {
        Write-Info 'Clearing any leftover data volume from a previous run...'
        Push-Location $RepoRoot
        try { & $docker @ComposeArgs down -v *> $null } catch { } finally { Pop-Location }
    }

    # --- build + run ---
    Write-Step 'Building and starting the stack (first build downloads images — please wait)'
    Push-Location $RepoRoot
    try {
        & $docker @ComposeArgs up -d --build
        if ($LASTEXITCODE -ne 0) { throw "docker compose up failed (exit $LASTEXITCODE)." }
    } finally {
        Pop-Location
    }

    Write-Step 'Waiting for the application to become healthy'
    if (Wait-Web -Url $WebUrl -TimeoutSec 360) {
        Write-Ok 'Application is up.'
        Start-Process $WebUrl
    } else {
        Write-Warn2 "The stack started but $WebUrl did not respond yet."
        Write-Warn2 'Give it another minute, then open the URL manually.'
    }

    Show-Completion -Creds $creds
}

# Prefer Docker's official installer with --accept-license: it pre-accepts the
# Docker Subscription Service Agreement, so the engine starts fully unattended
# (no first-run license dialog). winget cannot pass that flag, so it is only a
# fallback for when the direct download is unavailable.
$script:DockerInstallerUrl = 'https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe'

function Get-DockerInstaller {
    $installer = Join-Path $env:TEMP 'DockerDesktopInstaller.exe'
    if ((Test-Path $installer) -and ((Get-Item $installer).Length -gt 50MB)) { return $installer }
    try {
        Write-Info 'Downloading the Docker Desktop installer (~1 GB)...'
        Invoke-WebRequest -UseBasicParsing -Uri $script:DockerInstallerUrl -OutFile $installer
    } catch {
        Write-Warn2 "Direct download failed: $($_.Exception.Message)"
        return $null
    }
    if ((Test-Path $installer) -and ((Get-Item $installer).Length -gt 50MB)) { return $installer }
    return $null
}

function Install-DockerDesktop {
    $installer = Get-DockerInstaller
    if ($installer) {
        Write-Info 'Running the silent installer (license pre-accepted)...'
        Start-Process -FilePath $installer -ArgumentList 'install', '--quiet', '--accept-license' -Wait
    } else {
        $winget = Get-Command winget -ErrorAction SilentlyContinue
        if (-not $winget) {
            throw 'Could not download the Docker Desktop installer and winget is unavailable. Check the internet connection and re-run setup.bat.'
        }
        Write-Warn2 'Falling back to winget (may show a one-time license dialog on first start)...'
        & winget install --id Docker.DockerDesktop -e --silent `
            --accept-package-agreements --accept-source-agreements
    }
    Update-SessionPath
}

function Start-DockerDesktop {
    $exe = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if ((Test-Path $exe) -and -not (Get-Process 'Docker Desktop' -ErrorAction SilentlyContinue)) {
        Start-Process -FilePath $exe
    }
}

function Wait-DockerEngine { param($Docker, [int]$TimeoutSec = 300)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        # `docker info` fails (and writes to stderr) until the engine is ready.
        # Under EAP=Stop, the stream redirect would otherwise surface that as a
        # terminating NativeCommandError and abort setup, so swallow it and rely
        # on $LASTEXITCODE (the native exit code is set before any wrapping).
        try { & $Docker info *> $null } catch { }
        if ($LASTEXITCODE -eq 0) { return $true }
        Start-Sleep -Seconds 5
    }
    return $false
}

function Wait-Web { param($Url, [int]$TimeoutSec = 300)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($r.StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Seconds 5
    }
    return $false
}

# Create the repo-root .env, the backend .env.docker, and the Docker secret
# files.
#
# First configure (manifest.configured = false): OVERWRITE everything with
# freshly generated values. This deliberately replaces any secrets that may
# have travelled inside a zip of the developer's working tree (the project's
# secrets/ and .env.docker are gitignored but exist in plaintext on disk —
# see SEC-20 in the README), so the professor never runs on dev credentials.
#
# Subsequent runs (configured = true): keep the existing values. Regenerating
# the admin password after the database volume already exists would lock out
# the login, because ensure_admin_user() skips an admin that already exists.
function New-ProjectConfig {
    $secretsDir = Join-Path $RepoRoot 'secrets'
    $rootEnv    = Join-Path $RepoRoot '.env'
    $dockerEnv  = Join-Path $RepoRoot 'tutor-platform-api\.env.docker'
    $dbPass     = Join-Path $secretsDir 'db_password.txt'
    $jwtKey     = Join-Path $secretsDir 'jwt_secret_key.txt'
    $adminPwF   = Join-Path $secretsDir 'admin_password.txt'
    $prevKey    = Join-Path $secretsDir 'jwt_secret_key_previous.txt'

    $manifest = Get-Manifest
    if (-not $manifest.configured) {
        if (-not (Test-Path $secretsDir)) { New-Item -ItemType Directory -Path $secretsDir -Force | Out-Null }

        # Repo-root .env (no secrets — just DB_USER/DB_NAME/WEB_IP/DOMAIN).
        Copy-Item (Join-Path $RepoRoot '.env.example') $rootEnv -Force

        # Backend .env.docker — replace the placeholder admin username only.
        $tmpl  = Get-Content (Join-Path $RepoRoot 'tutor-platform-api\.env.docker.example') -Raw
        $owner = "owner_$(New-HexKey -Bytes 3)"   # owner_<6 hex>, satisfies the validator
        $tmpl  = $tmpl -replace '(?m)^ADMIN_USERNAME=.*$', "ADMIN_USERNAME=$owner"
        Write-TextFile $dockerEnv $tmpl

        # Docker secrets — all freshly generated and guaranteed to pass the
        # config + entrypoint validators (length, character classes, no placeholders).
        Write-TextFile $dbPass   (New-AlnumPassword)
        Write-TextFile $jwtKey   (New-HexKey -Bytes 32)
        Write-TextFile $adminPwF (New-StrongPassword)
        # Optional rotation slot — must exist (mounted as a secret) but empty is
        # the legitimate "no rotation in flight" signal.
        Write-TextFile $prevKey ''

        $manifest.configured = $true
        Save-Manifest $manifest
        Write-Ok 'Generated fresh secrets and env files.'
    } else {
        Write-Info 'Reusing the configuration from a previous run (keeps the existing login).'
    }

    # Read back what will actually be used so we can show the login at the end.
    $adminUser = (Get-Content $dockerEnv | Where-Object { $_ -match '^\s*ADMIN_USERNAME=' } |
                  Select-Object -First 1).Split('=', 2)[1].Trim()
    $adminPass = (Get-Content $adminPwF -Raw).Trim()
    [pscustomobject]@{ Username = $adminUser; Password = $adminPass }
}

function Show-Completion { param($Creds)
    Write-Host ''
    Write-Host '================================================================' -ForegroundColor Green
    Write-Host '   TMRP is running.' -ForegroundColor Green
    Write-Host '================================================================' -ForegroundColor Green
    Write-Host ''
    Write-Host "   Open in a browser : $WebUrl"
    Write-Host ''
    Write-Host '   Admin login (write this down):' -ForegroundColor Yellow
    Write-Host "     Username : $($Creds.Username)" -ForegroundColor Yellow
    Write-Host "     Password : $($Creds.Password)" -ForegroundColor Yellow
    Write-Host ''
    Write-Host '   Ready-made demo accounts (for trying the matching flow):'
    Write-Host '     Tutor  : tutor  / TutorDemo2026'
    Write-Host '     Parent : parent / ParentDemo2026'
    Write-Host ''
    Write-Host '   To remove everything afterwards, run teardown.bat.'
    Write-Host '================================================================' -ForegroundColor Green
}

# =============================================================================
#  Entry point
# =============================================================================
try {
    # Re-launch elevated if needed (the resume task already runs elevated).
    if (-not (Test-Admin)) {
        $a = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"")
        if ($Resume) { $a += '-Resume' }
        Start-Process -FilePath 'powershell.exe' -ArgumentList $a -Verb RunAs
        $script:HandingOff = $true   # the elevated copy owns the session; don't pause here
        exit
    }

    Write-Host '================================================================' -ForegroundColor Cyan
    Write-Host '   TMRP one-click setup' -ForegroundColor Cyan
    Write-Host '================================================================' -ForegroundColor Cyan

    if ($Resume) { Invoke-Phase2 } else { Invoke-Phase1 }
}
catch {
    Write-Host "`nERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Setup did not complete. Fix the issue above and re-run setup.bat.' -ForegroundColor Red
}
finally {
    if (-not $script:Rebooting -and -not $script:HandingOff) {
        Write-Host ''
        Read-Host 'Press Enter to close this window'
    }
}
