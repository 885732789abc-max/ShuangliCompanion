param()
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$python = Join-Path $root '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw '先按 README 创建 .venv' }
$configuration = @{
    mcpServers = @{
        shuangli_desktop = @{
            command = $python.Replace('\', '/')
            args = @((Join-Path $root 'desktop_mcp.py').Replace('\', '/'))
            cwd = $root.Replace('\', '/')
            startup_timeout_sec = 10
        }
    }
}
$target = Join-Path $root 'plugins/shuangli-desktop/.mcp.json'
$configuration | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $target -Encoding utf8
Write-Output "本机插件配置已写入：$target"
