from pydantic_settings import BaseSettings


class ConnectorConfig(BaseSettings):
    use_rabbitmq: bool = True
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_pass: str = "guest"
    rabbitmq_queue: str = "aisoc_alerts"

    wazuh_api_url: str = "http://localhost:55000"
    wazuh_api_user: str = "wazuh-wui"
    wazuh_api_pass: str = "wazuh-wui"
    wazuh_mock: bool = True

    opensearch_proxy_url: str = "https://127.0.0.1:4443"
    opensearch_proxy_user: str = "admin"
    opensearch_proxy_pass: str = ""
    opensearch_index_prefix: str = "wazuh-alerts-4.x-"

    connector_host: str = "0.0.0.0"
    connector_port: int = 8000
    connector_webhook_path: str = "/webhook/wazuh"

    model_config = {"env_file": ".env", "extra": "ignore"}
