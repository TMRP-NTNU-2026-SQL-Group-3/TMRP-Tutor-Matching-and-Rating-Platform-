# =============================================================================
#  TMRP teardown (Windows)
# -----------------------------------------------------------------------------
#  Reverses setup.ps1 and returns the machine to a clean state:
#    1. Stop the stack, delete its volumes and locally-built images.
#    2. Delete the generated .env / .env.docker / secret files.
#    3. Uninstall Docker Desktop and remove its WSL distros + data.
#    4. Disable the WSL + VirtualMachinePlatform features WE enabled.
#    5. Reboot to finish removing the Windows features.
#
#  An install manifest written by setup.ps1 records what setup actually
#  installed, so teardown only removes those pieces. If the manifest is missing
#  it falls back to best-effort removal.
# =============================================================================

$ErrorActionPreference = 'Continue'   # best-effort cleanup: keep going on errors
$ProgressPreference    = 'SilentlyContinue'   # speeds up the installer re-download in PS 5.1

$RepoRoot     = $PSScriptRoot
$StateDir     = Join-Path $env:LOCALAPPDATA 'TMRP-Setup'
$ManifestPath = Join-Path $StateDir 'install-manifest.json'
$TaskName     = 'TMRPSetupResume'
# Must match setup.ps1's project name so `down` targets what `up` created.
$ComposeArgs  = @('compose', '-p', 'tmrp', '-f', 'docker-compose.yml', '-f', 'docker-compose.run.yml')

$script:Rebooting = $false
$script:HandingOff = $false   # set when this process re-launches itself elevated

function Write-Step  { param($m) Write-Host "`n==> $m" -ForegroundColor Cyan }
function Write-Info  { param($m) Write-Host "    $m" -ForegroundColor Gray }
function Write-Ok    { param($m) Write-Host "    $m" -ForegroundColor Green }
function Write-Warn2 { param($m) Write-Host "    $m" -ForegroundColor Yellow }

function Test-Admin {
    $id = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object System.Security.Principal.WindowsPrincipal($id)).IsInRole(
        [System.Security.Principal.WindowsBuiltInRole]::Administrator)
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

function Get-Manifest {
    if (Test-Path $ManifestPath) {
        try {
            $m = Get-Content $ManifestPath -Raw | ConvertFrom-Json
            return [pscustomobject]@{
                wslEnabledByUs      = [bool]($m.wslEnabledByUs)
                vmpEnabledByUs      = [bool]($m.vmpEnabledByUs)
                dockerInstalledByUs = [bool]($m.dockerInstalledByUs)
                repoRoot            = if ($m.repoRoot) { $m.repoRoot } else { $RepoRoot }
            }
        } catch { }
    }
    # No manifest: assume we installed everything (best-effort full cleanup).
    [pscustomobject]@{
        wslEnabledByUs      = $true
        vmpEnabledByUs      = $true
        dockerInstalledByUs = $true
        repoRoot            = $RepoRoot
    }
}

# =============================================================================
function Remove-Stack {
    Write-Step 'Stopping the stack and removing volumes + local images'
    $docker = Get-DockerExe
    if (-not $docker) {
        Write-Warn2 'Docker CLI not found — skipping compose down (images/volumes go with the uninstall).'
        return
    }

    # Engine may be stopped; give it a short chance so the down is clean.
    $exe = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if ((Test-Path $exe) -and -not (Get-Process 'Docker Desktop' -ErrorAction SilentlyContinue)) {
        Start-Process -FilePath $exe
        for ($i = 0; $i -lt 24; $i++) {
            & $docker info *> $null
            if ($LASTEXITCODE -eq 0) { break }
            Start-Sleep -Seconds 5
        }
    }

    Push-Location $RepoRoot
    try {
        & $docker @ComposeArgs down -v --rmi local
    } catch {
        Write-Warn2 "compose down reported: $($_.Exception.Message)"
    } finally {
        Pop-Location
    }
}

function Remove-GeneratedFiles {
    Write-Step 'Deleting generated env and secret files'
    $targets = @(
        (Join-Path $RepoRoot '.env'),
        (Join-Path $RepoRoot 'tutor-platform-api\.env.docker'),
        (Join-Path $RepoRoot 'secrets\db_password.txt'),
        (Join-Path $RepoRoot 'secrets\jwt_secret_key.txt'),
        (Join-Path $RepoRoot 'secrets\admin_password.txt'),
        (Join-Path $RepoRoot 'secrets\jwt_secret_key_previous.txt')
    )
    foreach ($t in $targets) {
        if (Test-Path $t) {
            Remove-Item -Path $t -Force -ErrorAction SilentlyContinue
            Write-Info "Removed $([System.IO.Path]::GetFileName($t))"
        }
    }
    Write-Ok 'The .example templates are kept.'
}

function Stop-DockerProcesses {
    foreach ($p in 'Docker Desktop', 'com.docker.backend', 'com.docker.build', 'vpnkit') {
        Get-Process $p -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    }
    Get-Service 'com.docker.service' -ErrorAction SilentlyContinue |
        Stop-Service -Force -ErrorAction SilentlyContinue
}

function Uninstall-DockerDesktop {
    Write-Step 'Uninstalling Docker Desktop'
    Stop-DockerProcesses

    # Prefer the official installer's silent uninstall (symmetry with setup);
    # fall back to winget, then to a manual instruction.
    $installer = Join-Path $env:TEMP 'DockerDesktopInstaller.exe'
    if (-not ((Test-Path $installer) -and ((Get-Item $installer).Length -gt 50MB))) {
        try {
            Invoke-WebRequest -UseBasicParsing `
                -Uri 'https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe' `
                -OutFile $installer
        } catch { Write-Warn2 'Could not fetch the Docker installer for silent uninstall.' }
    }
    if ((Test-Path $installer) -and ((Get-Item $installer).Length -gt 50MB)) {
        Start-Process -FilePath $installer -ArgumentList 'uninstall', '--quiet' -Wait
    } elseif (Get-Command winget -ErrorAction SilentlyContinue) {
        & winget uninstall --id Docker.DockerDesktop -e --silent
    } else {
        Write-Warn2 'Please uninstall Docker Desktop manually from Settings > Apps.'
    }

    Write-Info 'Removing Docker WSL distros and leftover data...'
    foreach ($d in 'docker-desktop', 'docker-desktop-data') {
        try { wsl.exe --unregister $d *> $null } catch { }
    }
    foreach ($dir in @(
        (Join-Path $env:APPDATA      'Docker'),
        (Join-Path $env:LOCALAPPDATA 'Docker'),
        (Join-Path $env:ProgramData  'DockerDesktop'),
        (Join-Path $env:ProgramFiles 'Docker'))) {
        if (Test-Path $dir) { Remove-Item -Path $dir -Recurse -Force -ErrorAction SilentlyContinue }
    }
}

function Disable-WslPlatform { param($Manifest)
    $needReboot = $false
    Write-Step 'Removing WSL'
    try { wsl.exe --uninstall *> $null } catch { }

    if ($Manifest.vmpEnabledByUs) {
        Write-Info 'Disabling Virtual Machine Platform...'
        Disable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform -NoRestart | Out-Null
        $needReboot = $true
    }
    if ($Manifest.wslEnabledByUs) {
        Write-Info 'Disabling Windows Subsystem for Linux...'
        Disable-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux -NoRestart | Out-Null
        $needReboot = $true
    }
    return $needReboot
}

function Start-CountdownReboot {
    Write-Warn2 'A RESTART is required to finish removing the Windows features.'
    Write-Warn2 'The machine will restart in 10 seconds. Press Ctrl+C to cancel and reboot later.'
    for ($i = 10; $i -ge 1; $i--) { Write-Host "    restarting in $i ..." ; Start-Sleep -Seconds 1 }
    $script:Rebooting = $true
    Restart-Computer -Force
    exit
}

# =============================================================================
try {
    if (-not (Test-Admin)) {
        Start-Process -FilePath 'powershell.exe' `
            -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"") `
            -Verb RunAs
        $script:HandingOff = $true   # the elevated copy owns the session; don't pause here
        exit
    }

    Write-Host '================================================================' -ForegroundColor Cyan
    Write-Host '   TMRP teardown — removing the demo and its environment' -ForegroundColor Cyan
    Write-Host '================================================================' -ForegroundColor Cyan

    $manifest = Get-Manifest

    # Confirmation gate — teardown is destructive and irreversible. Do not run
    # this in your own development working tree: it deletes .env and the real
    # secrets/*.txt (templates are kept) and wipes the database volume.
    Write-Host ''
    Write-Warn2 'This will PERMANENTLY remove:'
    Write-Host '       - TMRP containers, the database volume, and locally built images'
    Write-Host '       - The generated .env / .env.docker / secrets/*.txt (.example templates kept)'
    if ($manifest.dockerInstalledByUs) { Write-Host '       - Docker Desktop (uninstalled)' }
    if ($manifest.wslEnabledByUs -or $manifest.vmpEnabledByUs) {
        Write-Host '       - WSL + Virtual Machine Platform (disabled; a reboot will follow)'
    }
    Write-Host "    Working folder: $RepoRoot" -ForegroundColor Gray
    Write-Host ''
    $confirm = Read-Host 'Type Y and press Enter to proceed (anything else cancels)'
    if ($confirm -notmatch '^(y|yes)$') {
        Write-Host 'Cancelled. Nothing was changed.' -ForegroundColor Yellow
        return
    }

    Remove-Stack
    Remove-GeneratedFiles

    $needReboot = $false
    if ($manifest.dockerInstalledByUs) { Uninstall-DockerDesktop }
    else { Write-Info 'Docker was already present before setup — leaving it installed.' }

    if ($manifest.wslEnabledByUs -or $manifest.vmpEnabledByUs) {
        $needReboot = Disable-WslPlatform -Manifest $manifest
    } else {
        Write-Info 'WSL was already present before setup — leaving it enabled.'
    }

    # Drop the resume task (if a half-finished setup left it) and the state dir.
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }
    if (Test-Path $StateDir) { Remove-Item -Path $StateDir -Recurse -Force -ErrorAction SilentlyContinue }

    Write-Host ''
    Write-Host '================================================================' -ForegroundColor Green
    Write-Host '   Teardown complete.' -ForegroundColor Green
    Write-Host '================================================================' -ForegroundColor Green

    if ($needReboot) { Start-CountdownReboot }
}
catch {
    Write-Host "`nERROR: $($_.Exception.Message)" -ForegroundColor Red
}
finally {
    if (-not $script:Rebooting -and -not $script:HandingOff) {
        Write-Host ''
        Read-Host 'Press Enter to close this window'
    }
}
