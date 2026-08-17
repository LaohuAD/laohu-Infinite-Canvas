#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_PATH="$LOG_DIR/openai-codex-cli-install-$(date +%Y%m%d-%H%M%S).log"

{
    echo "=== OpenAI Codex CLI install/update ==="
    echo "Workspace: $ROOT_DIR"
    echo ""

    if ! command -v curl >/dev/null 2>&1; then
        echo "curl is required. Install curl first, then run this script again."
        exit 1
    fi

    echo "Installing/updating Codex CLI with the OpenAI standalone installer..."
    if curl -fsSL https://chatgpt.com/codex/install.sh | sh; then
        :
    elif command -v npm >/dev/null 2>&1; then
        echo "Standalone installer was unavailable. Falling back to npm package install..."
        npm install -g @openai/codex
    else
        echo "Install failed, and npm is not available for fallback."
        exit 2
    fi

    echo ""
    if command -v codex >/dev/null 2>&1; then
        echo "Codex CLI found: $(command -v codex)"
        codex --version || true
        echo ""
        echo "安装完成。请在终端运行 'codex' 登录；本项目仅接入 OpenAI Codex CLI 的文本能力。"
    else
        echo "Codex CLI was installed, but 'codex' is not available in this shell PATH yet."
        echo "Open a new shell, then run: codex"
        exit 3
    fi

    echo ""
    echo "Log: $LOG_PATH"
} 2>&1 | tee -a "$LOG_PATH"
