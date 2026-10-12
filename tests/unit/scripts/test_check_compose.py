"""解析后 Compose 配置的安全契约。"""

from copy import deepcopy

import pytest
from scripts.check_compose import validate_compose


@pytest.fixture
def valid_config() -> dict[str, object]:
    services: dict[str, object] = {
        name: {}
        for name in ("mysql", "redis", "chroma", "migration", "api", "celery-worker", "web")
    }
    for name in ("api", "celery-worker"):
        services[name] = {
            "depends_on": {"migration": {"condition": "service_completed_successfully"}},
            "secrets": [
                {"source": "celery_broker_url", "target": "/run/secrets/celery_broker_url"}
            ],
            "volumes": [
                {"type": "volume", "source": "knowledge_data", "target": "/app/data/knowledge"}
            ],
        }
    services["mysql"] = {
        "volumes": [{"type": "volume", "source": "mysql_data", "target": "/var/lib/mysql"}]
    }
    services["redis"] = {"volumes": [{"type": "volume", "source": "redis_data", "target": "/data"}]}
    services["chroma"] = {
        "volumes": [{"type": "volume", "source": "chroma_data", "target": "/data"}]
    }
    services["web"] = {
        "ports": [{"host_ip": "127.0.0.1", "published": "8080", "target": 80}],
        "depends_on": {"api": {"condition": "service_healthy"}},
    }
    services["migration"] = {
        "depends_on": {
            "mysql": {"condition": "service_healthy"},
            "redis": {"condition": "service_healthy"},
        }
    }
    return {
        "services": services,
        "volumes": {
            name: {} for name in ("mysql_data", "redis_data", "chroma_data", "knowledge_data")
        },
    }


def test_valid_private_stack(valid_config: dict[str, object]) -> None:
    validate_compose(valid_config)


@pytest.mark.parametrize("service", ["mysql", "redis", "chroma", "api", "celery-worker"])
def test_rejects_exposed_internal_port(valid_config: dict[str, object], service: str) -> None:
    config = deepcopy(valid_config)
    config["services"][service]["ports"] = [{"published": "3306", "target": 3306}]  # type: ignore[index]
    with pytest.raises(ValueError, match="port"):
        validate_compose(config)


def test_rejects_non_loopback_web_port(valid_config: dict[str, object]) -> None:
    config = deepcopy(valid_config)
    config["services"]["web"]["ports"][0]["host_ip"] = "0.0.0.0"  # type: ignore[index]
    with pytest.raises(ValueError, match="web"):
        validate_compose(config)


@pytest.mark.parametrize("service", ["mysql", "redis", "chroma", "api", "web"])
def test_rejects_host_network_mode(valid_config: dict[str, object], service: str) -> None:
    config = deepcopy(valid_config)
    config["services"][service]["network_mode"] = "host"  # type: ignore[index]
    with pytest.raises(ValueError, match="network_mode"):
        validate_compose(config)


@pytest.mark.parametrize("service", ["api", "celery-worker"])
def test_requires_successful_migration(valid_config: dict[str, object], service: str) -> None:
    config = deepcopy(valid_config)
    config["services"][service]["depends_on"]["migration"]["condition"] = "service_started"  # type: ignore[index]
    with pytest.raises(ValueError, match="migration"):
        validate_compose(config)


@pytest.mark.parametrize("service", ["mysql", "chroma", "api", "celery-worker"])
def test_requires_persistent_business_volumes(
    valid_config: dict[str, object], service: str
) -> None:
    config = deepcopy(valid_config)
    config["services"][service]["volumes"] = []  # type: ignore[index]
    with pytest.raises(ValueError, match="volume"):
        validate_compose(config)


def test_rejects_fixed_container_names(valid_config: dict[str, object]) -> None:
    config = deepcopy(valid_config)
    config["services"]["api"]["container_name"] = "global-api"  # type: ignore[index]
    with pytest.raises(ValueError, match="container_name"):
        validate_compose(config)


def test_migration_waits_for_database_and_redis(valid_config: dict[str, object]) -> None:
    config = deepcopy(valid_config)
    config["services"]["migration"]["depends_on"]["mysql"]["condition"] = "service_started"  # type: ignore[index]
    with pytest.raises(ValueError, match="mysql"):
        validate_compose(config)


def test_web_waits_for_ready_api(valid_config: dict[str, object]) -> None:
    config = deepcopy(valid_config)
    config["services"]["web"]["depends_on"]["api"]["condition"] = "service_started"  # type: ignore[index]
    with pytest.raises(ValueError, match="api"):
        validate_compose(config)


@pytest.mark.parametrize("service", ["api", "celery-worker"])
def test_dispatchers_require_broker_secret(valid_config: dict[str, object], service: str) -> None:
    config = deepcopy(valid_config)
    config["services"][service]["secrets"] = []  # type: ignore[index]
    with pytest.raises(ValueError, match="celery_broker_url"):
        validate_compose(config)
