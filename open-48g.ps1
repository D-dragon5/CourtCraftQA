$ErrorActionPreference = 'Stop'
$projectDir = $PSScriptRoot
$configPath = Join-Path $projectDir 'remote.json'
if (-not (Test-Path -LiteralPath $configPath)) { throw '请复制 remote.example.json 为 remote.json，填写 SSH 地址和端口。' }
$settings = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$target = [string]$settings.ssh_target
$service = [string]$settings.service_name
if ($target -notmatch '^[A-Za-z0-9_][A-Za-z0-9_.@-]*$') { throw 'SSH 地址格式无效。' }
if ($service -notmatch '^[A-Za-z0-9_][A-Za-z0-9_.@-]*$') { throw '服务名格式无效。' }
$localPort = [int]$settings.local_port
$remotePort = [int]$settings.remote_port
$sshPort = if ($settings.ssh_port) { [int]$settings.ssh_port } else { 22 }
foreach ($port in @($localPort,$remotePort,$sshPort)) { if ($port -lt 1 -or $port -gt 65535) { throw '端口必须在 1 到 65535 之间。' } }
$forward = '127.0.0.1:{0}:127.0.0.1:{1}' -f $localPort,$remotePort
$listener = Get-NetTCPConnection -State Listen -LocalPort $localPort -ErrorAction SilentlyContinue
if ($listener) {
    $owner = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $listener[0].OwningProcess)
    if (-not $owner.CommandLine -or -not $owner.CommandLine.Contains($forward) -or -not $owner.CommandLine.Contains($target)) { throw "本机 $localPort 端口已被其他程序使用。" }
} else {
    $logDir = Join-Path $projectDir 'logs'
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $sshArgs = @('-T','-p',"$sshPort",'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o','ExitOnForwardFailure=yes','-o','ServerAliveInterval=30','-o','ServerAliveCountMax=3','-L',$forward)
    if ($settings.identity_file) {
        $identity = [Environment]::ExpandEnvironmentVariables([string]$settings.identity_file)
        if ($identity.StartsWith('~/') -or $identity.StartsWith('~\')) { $identity = Join-Path $env:USERPROFILE $identity.Substring(2) }
        if (-not (Test-Path -LiteralPath $identity)) { throw '找不到配置的 SSH 身份文件。' }
        $sshArgs += @('-i',('"' + $identity + '"'))
    }
    $sshArgs += @($target,('systemctl --user start ' + $service + ' && exec sleep infinity'))
    $tunnel = Start-Process -FilePath 'ssh.exe' -ArgumentList $sshArgs -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir 'remote-tunnel.log') -RedirectStandardError (Join-Path $logDir 'remote-tunnel-error.log') -PassThru
    $tunnel.Id | Set-Content -LiteralPath (Join-Path $logDir 'remote-tunnel.pid')
}
$ready = $false
for ($attempt=0; $attempt -lt 30; $attempt++) {
    try { Invoke-RestMethod "http://127.0.0.1:$localPort/api/health" -TimeoutSec 2 | Out-Null; $ready=$true; break }
    catch { Start-Sleep -Milliseconds 200 }
}
if (-not $ready) { throw '远程页面未就绪，请查看 logs/remote-tunnel-error.log。' }
Start-Process "http://127.0.0.1:$localPort"
