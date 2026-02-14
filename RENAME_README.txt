将「大创」文件夹改为英文的步骤
================================

方式一：PowerShell 命令（推荐）
------------------------------
1. 关闭 Cursor/VS Code（否则可能占用路径）
2. 打开 PowerShell，执行：

   cd D:\SJTU
   Rename-Item -Path "大创" -NewName "Dachuang"

3. 用新路径打开项目：D:\SJTU\Dachuang\CarbonCalculator


方式二：资源管理器
------------------------------
1. 关闭 Cursor/VS Code
2. 打开 D:\SJTU
3. 右键文件夹「大创」-> 重命名 -> 输入「Dachuang」
4. 用新路径打开项目
