param([string]$ConfigPath)
$ErrorActionPreference = 'Stop'
if (-not $ConfigPath) { $ConfigPath = Join-Path $PSScriptRoot 'config.json' }
if (-not [IO.Path]::IsPathRooted($ConfigPath)) { $ConfigPath = Join-Path $PSScriptRoot $ConfigPath }
if (-not (Test-Path -LiteralPath $ConfigPath)) { throw '找不到配置文件。' }
$settings = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$port = if ($env:COURTCRAFT_PORT) { [int]$env:COURTCRAFT_PORT } elseif ($settings.port) { [int]$settings.port } else { 5012 }
$listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
if (-not $listener) { Write-Output '该配置对应的服务已经关闭。'; exit 0 }
$running = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $listener[0].OwningProcess)
$scriptPath = Join-Path $PSScriptRoot 'token_viewer.py'
$pattern = '(?i)(?:^|[\s"])' + [regex]::Escape($scriptPath) + '(?=[\s"]|$)'
if (-not $running.CommandLine -or $running.CommandLine -notmatch $pattern) { throw '此端口由其他程序使用，未关闭。' }
Stop-Process -Id $running.ProcessId
Write-Output ("已关闭本项目在 $port 端口的服务。")
