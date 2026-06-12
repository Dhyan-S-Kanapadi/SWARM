import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

try:
    from mcp.client.streamable_http import streamable_http_client
except Exception:  # pragma: no cover - depends on installed MCP SDK version
    streamable_http_client = None


class TraeClient:
    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = Path(config_path or Path(__file__).with_name("mcp_config.json"))
        self.config = self._load_config()
        self.timeout_seconds = int(self.config.get("timeout_seconds", 900))
        self._validate_config()

    async def build_project(self, builder_prompt: str) -> dict[str, str]:
        return await asyncio.wait_for(self._build_project(builder_prompt), timeout=self.timeout_seconds)

    async def _build_project(self, builder_prompt: str) -> dict[str, str]:
        transport = self.config.get("transport", "stdio")
        if transport == "stdio":
            return await self._build_via_stdio(builder_prompt)
        if transport in {"streamable_http", "http"}:
            return await self._build_via_streamable_http(builder_prompt)
        raise ValueError(f"Unsupported MCP transport: {transport}")

    async def _build_via_stdio(self, builder_prompt: str) -> dict[str, str]:
        server = self.config["server"]
        command = server["command"]
        if not Path(command).exists() and shutil.which(command) is None:
            raise RuntimeError(f"trae.ai MCP command not found: {command}")

        params = StdioServerParameters(
            command=command,
            args=server.get("args", []),
            env=self._resolve_env(server.get("env", {})),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await self._call_build_tool(session, builder_prompt)

    async def _build_via_streamable_http(self, builder_prompt: str) -> dict[str, str]:
        if streamable_http_client is None:
            raise RuntimeError("Installed MCP SDK does not provide streamable_http_client")

        url = self.config["server"]["url"]
        async with streamable_http_client(url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await self._call_build_tool(session, builder_prompt)

    async def _call_build_tool(self, session: ClientSession, builder_prompt: str) -> dict[str, str]:
        tool_name = self.config.get("tool_name", "build_project")
        argument_name = self.config.get("argument_name", "prompt")
        arguments = {argument_name: builder_prompt}

        await self._assert_tool_exists(session, tool_name)
        result = await session.call_tool(tool_name, arguments=arguments)
        return self._extract_files(result)

    async def _assert_tool_exists(self, session: ClientSession, tool_name: str) -> None:
        tools_result = await session.list_tools()
        tools = getattr(tools_result, "tools", []) or []
        available = [tool.name for tool in tools]
        if available and tool_name not in available:
            raise RuntimeError(f"MCP tool '{tool_name}' not found. Available tools: {', '.join(available)}")

    def _extract_files(self, result: Any) -> dict[str, str]:
        structured = getattr(result, "structuredContent", None) or getattr(result, "structured_content", None)
        if structured:
            files = self._files_from_payload(structured)
            if files:
                return files

        content_items = getattr(result, "content", []) or []
        for item in content_items:
            if isinstance(item, types.TextContent):
                files = self._files_from_text(item.text)
                if files:
                    return files

        raise RuntimeError("trae.ai MCP response did not include generated files")

    def _files_from_text(self, text: str) -> dict[str, str]:
        try:
            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`").removeprefix("json").strip()
            return self._files_from_payload(json.loads(cleaned))
        except json.JSONDecodeError:
            return {}

    def _files_from_payload(self, payload: Any) -> dict[str, str]:
        if not isinstance(payload, dict):
            return {}

        candidates = payload.get("files") or payload.get("code_files") or payload.get("generated_files")
        if isinstance(candidates, dict):
            return {str(path): str(content) for path, content in candidates.items()}

        if isinstance(candidates, list):
            files: dict[str, str] = {}
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                path = item.get("path") or item.get("filepath") or item.get("filename")
                content = item.get("content") or item.get("code")
                if path and content is not None:
                    files[str(path)] = str(content)
            return files

        return {}

    def _load_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Missing MCP config: {self.config_path}")
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    def _validate_config(self) -> None:
        transport = self.config.get("transport", "stdio")
        server = self.config.get("server")
        if not isinstance(server, dict):
            raise ValueError("mcp_config.json must contain a server object")
        if transport == "stdio" and not server.get("command"):
            raise ValueError("stdio MCP config requires server.command")
        if transport in {"streamable_http", "http"} and not server.get("url"):
            raise ValueError("streamable_http MCP config requires server.url")
        if transport not in {"stdio", "streamable_http", "http"}:
            raise ValueError(f"Unsupported MCP transport: {transport}")

    def _resolve_env(self, env: dict[str, str]) -> dict[str, str]:
        resolved = os.environ.copy()
        for key, value in env.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                resolved[key] = os.getenv(value[2:-1], "")
            else:
                resolved[key] = str(value)
        return resolved
