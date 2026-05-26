from pydantic_settings import BaseSettings


class ConnectorConfig(BaseSettings):
    use_rabbitmq: bool = False
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_pass: str = "guest"
    rabbitmq_queue: str = "aisoc_alerts"

    wazuh_api_url: str = "https://localhost:55000"
    wazuh_api_user: str = ""
    wazuh_api_pass: str = ""

    wazuh_verify_ssl: bool = False

    wazuh_manager_api_url: str = ""
    wazuh_manager_api_user: str = ""
    wazuh_manager_api_pass: str = ""

    indexer_url: str = "https://localhost:9200"
    indexer_user: str = "admin"
    indexer_pass: str = ""
    indexer_prefix: str = "wazuh-alerts-4.x-"

    connector_host: str = "0.0.0.0"
    connector_port: int = 8000
    connector_webhook_path: str = "/webhook/wazuh"

    model_config = {"env_file": ".env", "extra": "ignore"}
