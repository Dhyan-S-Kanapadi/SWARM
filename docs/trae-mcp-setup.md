# Trae MCP Setup

SWARM.AI exposes an MCP server named `swarm_ai`. Trae must act as the MCP client/host and call SWARM tools.

## Local Trae

Use `.trae/mcp.json`.

This config starts the MCP server through local stdio:

```json
{
  "mcpServers": {
    "swarm_ai": {
      "command": "D:\\SWARM.AI\\.venv\\Scripts\\python.exe",
      "args": ["D:\\SWARM.AI\\backend\\mcp\\swarm_server.py"]
    }
  }
}
```

This works only when Trae is running on the same Windows machine as SWARM.AI.

## Trae Cloud Or URL-Based MCP

Cloud Trae cannot execute `D:\SWARM.AI\.venv\Scripts\python.exe` on your laptop. Run SWARM MCP as HTTP:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_swarm_mcp_http.ps1
```

Local URL:

```text
http://127.0.0.1:8931/mcp
```

For Trae Cloud, expose that URL with a tunnel such as ngrok or Cloudflare Tunnel and use the public `/mcp` URL in Trae.

Example:

```json
{
  "mcpServers": {
    "swarm_ai": {
      "url": "https://your-public-tunnel-url/mcp"
    }
  }
}
```

## Expected Tools

Trae should show these `swarm_ai` tools:

- `list_swarm_runs`
- `get_builder_prompt`
- `get_project_context`
- `get_quality_report`
- `get_submitted_code_files`
- `submit_code_files`
- `mark_builder_error`

## Builder Handoff Test

After a SWARM run reaches `waiting_for_trae`, send this in Trae:

```text
Use the swarm_ai MCP server.
Call get_project_context for the latest run.
Build the complete MVP from builder_prompt.
When finished, call submit_code_files with the full project file map.
```

If Trae lists the tools but does not call them, explicitly mention the tool names:

```text
Call swarm_ai.get_project_context first. After generating files, call swarm_ai.submit_code_files. Do not only print code.
```

## Common Failure

If Analyst and Architect work but Builder stays stuck, SWARM is not broken. Builder is waiting for Trae to call `submit_code_files`.

Use Local Trae with `.trae/mcp.json`, or use the HTTP MCP server plus a public tunnel for Trae Cloud.
