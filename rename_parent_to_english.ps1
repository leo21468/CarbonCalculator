# 将父目录「大创」重命名为英文「Dachuang」
# 请在资源管理器中右键「使用 PowerShell 运行」，或关闭 IDE 后手动执行
$parent = Split-Path -Parent $PSScriptRoot
$currentName = Split-Path -Leaf $PSScriptRoot
$grandparent = Split-Path -Parent $parent
$oldPath = Join-Path $grandparent "大创"
$newPath = Join-Path $grandparent "Dachuang"

if (Test-Path $oldPath) {
    Write-Host "即将重命名: $oldPath -> $newPath"
    Rename-Item -Path $oldPath -NewName "Dachuang"
    Write-Host "完成。请用新路径打开项目: $newPath\CarbonCalculator"
} else {
    Write-Host "未找到路径: $oldPath"
    Write-Host "当前脚本目录: $PSScriptRoot"
}
