from pydantic_settings import BaseSettings
import os

class ConnectorConfig(BaseSettings):
    use_rabbitmq: bool = False
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_pass: str = "guest"
    rabbitmq_queue: str = "aisoc_alerts"

    wazuh_api_url: str = os.getenv("WAZUH_API_URL")
    wazuh_api_user: str = os.getenv("WAZUH_API_USER")
    wazuh_api_pass: str = os.getenv("WAZUH_API_PASS")
    
    wazuh_verify_ssl: bool = False
    
    wazuh_manager_api_url: str = os.getenv("WAZUH_API_MANAGER_URL", "")
    wazuh_manager_api_user: str = os.getenv("WAZUH_API_MANAGER_USER", "")
    wazuh_manager_api_pass: str = os.getenv("WAZUH_API_MANAGER_PASS", "")

    indexer_url: str = os.getenv("WAZUH_API_INDEXER_URL", "https://localhost:9200")
    indexer_user: str = os.getenv("WAZUH_API_INDEXER_USER", "admin")
    indexer_pass: str = os.getenv("WAZUH_API_INDEXER_PASS", "")
    indexer_prefix: str = os.getenv("WAZUH_API_INDEXER_ALERT", "wazuh-alerts-4.x-")

    connector_host: str = "0.0.0.0"
    connector_port: int = 8000
    connector_webhook_path: str = "/webhook/wazuh"

    model_config = {"env_file": ".env", "extra": "ignore"}
