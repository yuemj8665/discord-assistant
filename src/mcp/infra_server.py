#!/usr/bin/env python3
"""홈서버 인프라 정보를 MCP 도구로 노출하는 로컬 MCP 서버."""
import json
import subprocess
import sys

import psutil
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

app = Server("infra")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_server_resources",
            description="현재 홈서버의 CPU, 메모리, 디스크 사용률을 반환합니다.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="get_docker_containers",
            description="현재 실행 중이거나 중지된 Docker 컨테이너 목록을 반환합니다.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "get_server_resources":
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        data = {
            "cpu_percent": round(cpu, 1),
            "memory_percent": round(mem.percent, 1),
            "memory_used_gb": round(mem.used / 1024 ** 3, 1),
            "memory_total_gb": round(mem.total / 1024 ** 3, 1),
            "disk_percent": round(disk.percent, 1),
            "disk_used_gb": round(disk.used / 1024 ** 3, 1),
            "disk_total_gb": round(disk.total / 1024 ** 3, 1),
        }
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

    if name == "get_docker_containers":
        try:
            result = subprocess.run(
                ["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}"],
                capture_output=True, text=True, timeout=10,
            )
            containers = []
            for line in result.stdout.strip().splitlines():
                if not line:
                    continue
                parts = line.split("\t", 2)
                containers.append({
                    "name": parts[0],
                    "status": parts[1] if len(parts) > 1 else "unknown",
                    "image": parts[2] if len(parts) > 2 else "unknown",
                    "is_up": parts[1].lower().startswith("up") if len(parts) > 1 else False,
                })
            return [TextContent(type="text", text=json.dumps(containers, ensure_ascii=False))]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    return [TextContent(type="text", text=f"알 수 없는 도구: {name}")]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
