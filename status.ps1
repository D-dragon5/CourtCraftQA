param([string]$ConfigPath)
$ErrorActionPreference = 'Stop'
$projectDir = $PSScriptRoot
if (-not $ConfigPath) { $ConfigPath = Join-Path $projectDir 'config.json' }
if (-not [IO.Path]::IsPathRooted($ConfigPath)) { $ConfigPath = Join-Path $projectDir $ConfigPath }
$settings = $null
if (Test-Path -LiteralPath $ConfigPath) {
    $settings = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
}
$port = if ($env:COURTCRAFT_PORT) { [int]$env:COURTCRAFT_PORT } elseif ($settings.port) { [int]$settings.port } else { 5012 }
if ($port -lt 1 -or $port -gt 65535) { throw '端口必须在 1 到 65535 之间。' }
$url = "http://127.0.0.1:$port"
Write-Output 'CourtCraftQA 运行状态'
Write-Output ("项目位置：$projectDir")
Write-Output ("网页地址：$url")
$listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
if (-not $listener) {
    Write-Output '状态：未运行。双击 start.bat 即可启动。'
    if (-not $settings) { Write-Output '尚未生成配置；首次启动会自动创建。' }
    exit 0
}
$scriptPath = Join-Path $projectDir 'token_viewer.py'
$pattern = '(?i)(?:^|[\s"])' + [regex]::Escape($scriptPath) + '(?=[\s"]|$)'
$running = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $listener[0].OwningProcess)
if (-not $running.CommandLine -or $running.CommandLine -notmatch $pattern) {
    Write-Output ("状态：本项目未运行；端口 $port 正被其他程序使用。")
    Write-Output '请检查已启动的程序，或在 config.json 修改 port 后重新启动。'
    exit 0
}
Write-Output ("进程：" + $running.ProcessId)
try {
    $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 3
    if ($health.status -ne 'ok') { throw '健康检查尚未通过。' }
    Write-Output '状态：正在运行，网页响应正常。'
    if ($health.data_root) { Write-Output ("数据目录：" + $health.data_root) }
    if ($null -ne $health.videos) { Write-Output ("视频数量：" + $health.videos) }
} catch {
    Write-Output '状态：进程存在，但网页尚未响应。若持续如此，请查看错误日志。'
}
Write-Output ("错误日志：" + (Join-Path $projectDir "logs\viewer-$port-error.log"))
Write-Output '仅关闭浏览器不会停止后台服务。使用结束后双击 stop.bat。'
