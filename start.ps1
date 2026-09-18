#Requires -Version 5.1
<#
.SYNOPSIS
  一键启动 WorkBuddy2API（Windows）。

.DESCRIPTION
  检查 Python 与依赖 → 预检 token → 启动 uvicorn。
  token 来源：CODEBUDDY_AUTH_TOKEN 环境变量，或项目根目录的 tokens.json。

.EXAMPLE
  .\start.ps1
  .\start.ps1 -Port 9000
  $env:API_KEY='my-key'; $env:CODEBUDDY_AUTH_TOKEN='<token>'; .\start.ps1
#>
[CmdletBinding()]
param(
    [int]$Port = 8000,
    [string]$BindHost = '0.0.0.0',
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Step($text) { Write-Host "[*] $text" -ForegroundColor Cyan }
function Ok($text)   { Write-Host "[+] $text" -ForegroundColor Green }
function Warn($text) { Write-Host "[!] $text" -ForegroundColor Yellow }

# ── 1. 定位 Python ─────────────────────────────────────────────────────────
$python = $null
$pythonPrefix = @()
if (Get-Command python -ErrorAction SilentlyContinue) {
    $python = 'python'
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $python = 'py'
    $pythonPrefix = @('-3')
}
if (-not $python) {
    throw '未找到 python，请先安装 Python 3.10+ 并加入 PATH'
}
$version = (& $python @pythonPrefix --version 2>&1) -join ' '
Ok "Python: $version"

# ── 2. 检查依赖 ────────────────────────────────────────────────────────────
& $python @pythonPrefix -c 'import fastapi, uvicorn' 2>$null
if ($LASTEXITCODE -ne 0) {
    if ($SkipInstall) {
        throw '缺少依赖 fastapi / uvicorn（已指定 -SkipInstall，未自动安装）'
    }
    Warn '缺少依赖 fastapi / uvicorn，正在安装...'
    & $python @pythonPrefix -m pip install fastapi uvicorn
    if ($LASTEXITCODE -ne 0) { throw '依赖安装失败，请手动执行: pip install fastapi uvicorn' }
}
Ok '依赖检查通过 (fastapi / uvicorn)'

# ── 3. 预检 token ─────────────────────────────────────────────────────────
& $python @pythonPrefix -c 'import codebuddy_direct_api as m; m.find_and_load_token()' 2>$null
if ($LASTEXITCODE -ne 0) {
    Warn '未能加载 token：请设置 CODEBUDDY_AUTH_TOKEN 环境变量，或在项目根目录放置 tokens.json'
    Warn '服务仍会启动，但 /v1/chat/completions 会返回 503'
} else {
    Ok 'token 加载成功'
}

# ── 4. 启动 ───────────────────────────────────────────────────────────────
$env:PORT = "$Port"
Write-Host ''
Ok "启动中：http://127.0.0.1:$Port"
Write-Host "    健康检查   http://127.0.0.1:$Port/health"
Write-Host "    模型列表   http://127.0.0.1:$Port/v1/models"
Write-Host "    OpenAI 兼容 base_url   http://127.0.0.1:$Port/v1"
Write-Host ''
Write-Host '    接入 CC Switch：新增 provider，base_url 填上面的地址，apiFormat 选 openai_chat' -ForegroundColor DarkGray
Write-Host '    详见 docs/codex-integration.md   （Ctrl+C 停止服务）' -ForegroundColor DarkGray
Write-Host ''

& $python @pythonPrefix -m uvicorn server:app --host $BindHost --port $Port --log-level info
exit $LASTEXITCODE