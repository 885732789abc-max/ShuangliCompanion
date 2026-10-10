param([string]$TunnelId)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$client = Join-Path $projectRoot 'tools/openai-tunnel/tunnel-client.exe'
$profileDirectory = Join-Path $projectRoot 'data/tunnel-profiles'
if (-not $TunnelId) { $TunnelId = Read-Host 'OpenAI tunnel_id' }
if ($TunnelId -notmatch '^tunnel_[A-Za-z0-9_-]+$') { throw 'Invalid tunnel_id' }
if (-not (Test-Path -LiteralPath $client)) { throw 'Missing tools/openai-tunnel/tunnel-client.exe' }
$previousKey = $env:CONTROL_PLANE_API_KEY
$keyPointer = [IntPtr]::Zero
try {
    if (-not $env:CONTROL_PLANE_API_KEY) {
        $runtimeKey = Read-Host 'OpenAI tunnel runtime key' -AsSecureString
        $keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($runtimeKey)
        $env:CONTROL_PLANE_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
        $keyPointer = [IntPtr]::Zero
    }
    $pythonPath = (Join-Path $projectRoot '.venv/Scripts/python.exe').Replace('\','/')
    $serverPath = (Join-Path $projectRoot 'desktop_mcp.py').Replace('\','/')
    $mcpCommand = '"' + $pythonPath + '" "' + $serverPath + '"'
    & $client init --sample sample_mcp_stdio_local --profile shuangli-chat --profile-dir $profileDirectory --tunnel-id $TunnelId --mcp-command $mcpCommand --health-listen-addr '127.0.0.1:0' --force
    if ($LASTEXITCODE -ne 0) { throw 'Tunnel profile creation failed' }
    & $client run --profile shuangli-chat --profile-dir $profileDirectory
} finally {
    if ($keyPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer) }
    $env:CONTROL_PLANE_API_KEY = $previousKey
}
