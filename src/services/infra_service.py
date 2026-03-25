import subprocess
import logging
from dataclasses import dataclass

import psutil

logger = logging.getLogger(__name__)


@dataclass
class ResourceStatus:
    cpu: float       # %
    memory: float    # %
    disk: float      # %
    memory_used_gb: float
    memory_total_gb: float
    disk_used_gb: float
    disk_total_gb: float


@dataclass
class ContainerInfo:
    name: str
    status: str      # "Up 2 hours" / "Exited (0) ..."
    is_up: bool


class InfraService:
    """홈서버 리소스 및 Docker 컨테이너 상태 조회."""

    def get_resources(self) -> ResourceStatus:
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        return ResourceStatus(
            cpu=cpu,
            memory=mem.percent,
            disk=disk.percent,
            memory_used_gb=round(mem.used / 1024 ** 3, 1),
            memory_total_gb=round(mem.total / 1024 ** 3, 1),
            disk_used_gb=round(disk.used / 1024 ** 3, 1),
            disk_total_gb=round(disk.total / 1024 ** 3, 1),
        )

    def get_containers(self) -> list[ContainerInfo]:
        try:
            result = subprocess.run(
                ["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Status}}"],
                capture_output=True, text=True, timeout=10,
            )
            containers = []
            for line in result.stdout.strip().splitlines():
                if not line:
                    continue
                parts = line.split("\t", 1)
                name = parts[0]
                status = parts[1] if len(parts) > 1 else "unknown"
                containers.append(ContainerInfo(
                    name=name,
                    status=status,
                    is_up=status.lower().startswith("up"),
                ))
            return containers
        except Exception as e:
            logger.error("[Infra] Docker 조회 실패: %s", e)
            return []

    def format_resource_report(self, res: ResourceStatus) -> str:
        return (
            f"**홈서버 리소스 현황**\n"
            f"├ CPU: `{res.cpu:.1f}%`\n"
            f"├ 메모리: `{res.memory:.1f}%` ({res.memory_used_gb}GB / {res.memory_total_gb}GB)\n"
            f"└ 디스크: `{res.disk:.1f}%` ({res.disk_used_gb}GB / {res.disk_total_gb}GB)"
        )

    def format_container_report(self, containers: list[ContainerInfo]) -> str:
        if not containers:
            return "**Docker 컨테이너**: 조회 실패 또는 없음"
        lines = ["**Docker 컨테이너 현황**"]
        for c in containers:
            icon = "🟢" if c.is_up else "🔴"
            lines.append(f"{icon} `{c.name}` — {c.status}")
        return "\n".join(lines)
