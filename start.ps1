param([string]$ConfigPath)
$ErrorActionPreference = 'Stop'
$projectDir = $PSScriptRoot
$firstRunConfig = -not $ConfigPath
if (-not $ConfigPath) { $ConfigPath = Join-Path $projectDir 'config.json' }
if (-not [IO.Path]::IsPathRooted($ConfigPath)) { $ConfigPath = Join-Path $projectDir $ConfigPath }
if (-not (Test-Path -LiteralPath $ConfigPath)) {
    if (-not $firstRunConfig) { throw '找不到指定配置。演示请先运行 scripts/prepare_demo.py。' }
    $initial = Get-Content -LiteralPath (Join-Path $projectDir 'config.example.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $initial.data_root = 'data'
    New-Item -ItemType Directory -Path (Join-Path $projectDir 'data') -Force | Out-Null
    $initial | ConvertTo-Json | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
}
$settings = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$port = if ($env:COURTCRAFT_PORT) { [int]$env:COURTCRAFT_PORT } elseif ($settings.port) { [int]$settings.port } else { 5012 }
if ($port -lt 1 -or $port -gt 65535) { throw '端口必须在 1 到 65535 之间。' }
$embeddedPython = Join-Path $projectDir 'runtime\python.exe'
if (Test-Path -LiteralPath $embeddedPython) { $pythonPath = $embeddedPython }
else { $pythonPath = (Get-Command python -ErrorAction Stop).Source }
$scriptPath = Join-Path $projectDir 'token_viewer.py'
$listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
if ($listener) {
    $running = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $listener[0].OwningProcess)
    $pattern = '(?i)(?:^|[\s"])' + [regex]::Escape($scriptPath) + '(?=[\s"]|$)'
    if (-not $running.CommandLine -or $running.CommandLine -notmatch $pattern) { throw "端口 $port 已被其他程序使用。" }
} else {
    $logDir = Join-Path $projectDir 'logs'
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    Start-Process -FilePath $pythonPath -ArgumentList @('-X', 'utf8', '-u', ('"' + $scriptPath + '"'), '--config', ('"' + $ConfigPath + '"')) -WorkingDirectory $projectDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir "viewer-$port.log") -RedirectStandardError (Join-Path $logDir "viewer-$port-error.log")
}
$ready = $false
for ($attempt=0; $attempt -lt 30; $attempt++) {
    try { Invoke-RestMethod "http://127.0.0.1:$port/api/health" -TimeoutSec 2 | Out-Null; $ready=$true; break }
    catch { Start-Sleep -Milliseconds 200 }
}
if (-not $ready) { throw '网页未正常启动，请查看 logs 文件夹中的错误日志。' }
Start-Process "http://127.0.0.1:$port"
