param([string]$DesktopPath)
$ErrorActionPreference = 'Stop'
$projectDir = $PSScriptRoot
if (-not $DesktopPath) { $DesktopPath = [Environment]::GetFolderPath('DesktopDirectory') }
if (-not $DesktopPath -or -not (Test-Path -LiteralPath $DesktopPath -PathType Container)) {
    throw '找不到可写的桌面文件夹。可以直接使用项目目录中的 start.bat、status.bat、stop.bat。'
}
$entries = @(
    @{ Name = 'CourtCraftQA 启动'; File = 'start.bat'; Description = '启动本机 CourtCraftQA 并打开网页' },
    @{ Name = 'CourtCraftQA 查看状态'; File = 'status.bat'; Description = '查看本机 CourtCraftQA 是否正在运行' },
    @{ Name = 'CourtCraftQA 停止'; File = 'stop.bat'; Description = '停止此目录对应的 CourtCraftQA 后台服务' }
)
$shell = New-Object -ComObject WScript.Shell
try {
    foreach ($entry in $entries) {
        $target = Join-Path $projectDir $entry.File
        if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw ("缺少文件：" + $entry.File) }
        $shortcutPath = Join-Path $DesktopPath ($entry.Name + '.lnk')
        $suffix = 0
        while (Test-Path -LiteralPath $shortcutPath) {
            $existing = $shell.CreateShortcut($shortcutPath)
            $sameTarget = [string]::Equals($existing.TargetPath, $target, [StringComparison]::OrdinalIgnoreCase)
            [void][Runtime.InteropServices.Marshal]::ReleaseComObject($existing)
            if ($sameTarget) { break }
            $suffix++
            $shortcutPath = Join-Path $DesktopPath ($entry.Name + ' (' + $suffix + ').lnk')
        }
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $target
        $shortcut.WorkingDirectory = $projectDir
        $shortcut.Description = $entry.Description
        $shortcut.WindowStyle = 1
        $icon = Join-Path $projectDir 'runtime\python.exe'
        if (Test-Path -LiteralPath $icon) { $shortcut.IconLocation = $icon + ',0' }
        $shortcut.Save()
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($shortcut)
        Write-Output ("已创建：" + $shortcutPath)
    }
} finally {
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($shell)
}
Write-Output '完成。无需管理员权限，也无需安装 Python 或额外环境。'
Write-Output '快捷方式指向当前文件夹；移动文件夹后，请在新位置重新运行本脚本。'
