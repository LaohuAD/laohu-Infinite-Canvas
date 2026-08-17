param(
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logPath = Join-Path $logDir ("openai-codex-cli-install-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
Start-Transcript -Path $logPath -Force | Out-Null

function Pause-End {
    Write-Host ""
    Write-Host "Log: $logPath"
    Read-Host "Press Enter to close"
    Stop-Transcript | Out-Null
}

function Get-NpmCommand {
    $npmCmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($npmCmd) { return $npmCmd.Source }

    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if ($npm) { return $npm.Source }

    return $null
}

function Add-NpmPrefixToPath {
    param([string]$NpmCommand)

    try {
        $prefix = (& $NpmCommand config get prefix 2>$null | Select-Object -First 1).Trim()
        if ($prefix -and (Test-Path -LiteralPath $prefix)) {
            $env:PATH = "$prefix;$env:PATH"
        }
    } catch {
        Write-Host "Could not read npm global prefix. Continuing with the current PATH."
    }
}

function Install-WithNpmFallback {
    $npm = Get-NpmCommand
    if (-not $npm) {
        throw "OpenAI standalone installer failed, and npm was not found for fallback install."
    }

    Write-Host "Falling back to npm package install: npm install -g @openai/codex"
    & $npm install -g "@openai/codex"
    if ($LASTEXITCODE -ne 0) {
        throw "npm fallback install failed with exit code $LASTEXITCODE."
    }
    Add-NpmPrefixToPath -NpmCommand $npm
}

try {
    Write-Host "=== OpenAI Codex CLI install/update ==="
    Write-Host "Workspace: $root"
    Write-Host ""

    if ($NonInteractive) {
        $env:CODEX_NON_INTERACTIVE = "1"
        Write-Host "CODEX_NON_INTERACTIVE=1"
    }

    Write-Host "Installing/updating Codex CLI with the official OpenAI standalone installer..."
    try {
        irm https://chatgpt.com/codex/install.ps1 | iex
    } catch {
        Write-Host "Standalone installer failed: $($_.Exception.Message)"
        Install-WithNpmFallback
    }
    Write-Host ""

    $codex = Get-Command codex -ErrorAction SilentlyContinue
    if (-not $codex) {
        Write-Host "Codex CLI was installed, but 'codex' is not available in this PowerShell PATH yet."
        Write-Host "Close this window, open a new PowerShell, then run: codex"
        Pause-End
        exit 2
    }

    Write-Host "Codex CLI found: $($codex.Source)"
    try {
        & codex --version
    } catch {
        Write-Host "Could not read Codex version in this session. Open a new PowerShell and run: codex --version"
    }
    Write-Host ""
    Write-Host "安装完成。请在 PowerShell 运行 'codex' 登录；本项目仅接入 OpenAI Codex CLI 的文本能力。"
    Write-Host "You can also double-click CLI\windows\openai\start_openai_codex_cli.bat."
    Pause-End
} catch {
    Write-Host "Error: $($_.Exception.Message)"
    Pause-End
    exit 1
}
