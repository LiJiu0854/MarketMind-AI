"""检查解析后的默认单机 Compose 是否保持部署安全边界。"""

import json
import sys

REQUIRED_SERVICES = ("mysql", "redis", "chroma", "migration", "api", "celery-worker", "web")
PERSISTENT_MOUNTS = {
    "mysql": ("mysql_data", "/var/lib/mysql"),
    "redis": ("redis_data", "/data"),
    "chroma": ("chroma_data", "/data"),
    "api": ("knowledge_data", "/app/data/knowledge"),
    "celery-worker": ("knowledge_data", "/app/data/knowledge"),
}


def validate_compose(config: dict[str, object]) -> None:
    """违背内网、启动门禁或持久化契约时抛出不含密钥的错误。"""
    services = config.get("services")
    volumes = config.get("volumes")
    if not isinstance(services, dict) or not isinstance(volumes, dict):
        raise ValueError("services/volumes missing")
    for name in REQUIRED_SERVICES:
        if not isinstance(services.get(name), dict):
            raise ValueError(f"service {name} missing")

    for name, service in services.items():
        if not isinstance(service, dict):
            raise ValueError("invalid service")
        if service.get("container_name"):
            raise ValueError(f"{name}: container_name is forbidden")
        if service.get("network_mode") is not None:
            raise ValueError(f"{name}: network_mode is forbidden")
        if name != "web" and service.get("ports"):
            raise ValueError(f"{name}: published port is forbidden")

    web = services["web"]
    ports = web.get("ports")
    if not isinstance(ports, list) or len(ports) != 1 or not isinstance(ports[0], dict):
        raise ValueError("web must publish exactly one loopback port")
    port = ports[0]
    if (port.get("host_ip"), str(port.get("published")), port.get("target")) != (
        "127.0.0.1",
        "8080",
        80,
    ):
        raise ValueError("web must publish only 127.0.0.1:8080:80")

    for name in ("api", "celery-worker"):
        depends = services[name].get("depends_on")
        if (
            not isinstance(depends, dict)
            or depends.get("migration", {}).get("condition") != "service_completed_successfully"
        ):
            raise ValueError(f"{name}: migration must complete successfully")
        secrets = services[name].get("secrets")
        if not isinstance(secrets, list) or not any(
            isinstance(secret, dict) and secret.get("source") == "celery_broker_url"
            for secret in secrets
        ):
            raise ValueError(f"{name}: celery_broker_url secret missing")
    for dependency in ("mysql", "redis"):
        depends = services["migration"].get("depends_on")
        if (
            not isinstance(depends, dict)
            or depends.get(dependency, {}).get("condition") != "service_healthy"
        ):
            raise ValueError(f"migration must wait for healthy {dependency}")
    depends = web.get("depends_on")
    if (
        not isinstance(depends, dict)
        or depends.get("api", {}).get("condition") != "service_healthy"
    ):
        raise ValueError("web must wait for healthy api")

    for name, (source, target) in PERSISTENT_MOUNTS.items():
        mounts = services[name].get("volumes")
        if (
            source not in volumes
            or not isinstance(mounts, list)
            or not any(
                isinstance(mount, dict)
                and mount.get("type") == "volume"
                and mount.get("source") == source
                and mount.get("target") == target
                for mount in mounts
            )
        ):
            raise ValueError(f"{name}: persistent volume {source} missing")


if __name__ == "__main__":
    try:
        validate_compose(json.load(sys.stdin))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"Compose contract failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
