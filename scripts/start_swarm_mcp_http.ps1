param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8931
)

$ErrorActionPreference = "Stop"

$env:SWARM_MCP_TRANSPORT = "streamable-http"
$env:SWARM_MCP_HOST = $HostName
$env:SWARM_MCP_PORT = [string]$Port

Write-Host "Starting SWARM.AI MCP HTTP server..."
Write-Host "Local MCP URL: http://$HostName`:$Port/mcp"
Write-Host "Use this URL directly in Trae Local if it supports remote MCP URLs."
Write-Host "For Trae Cloud, expose this URL with a tunnel such as ngrok or Cloudflare Tunnel."

& "D:\SWARM.AI\.venv\Scripts\python.exe" "D:\SWARM.AI\backend\mcp\swarm_server.py"
