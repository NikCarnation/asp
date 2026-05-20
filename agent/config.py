from pydantic_settings import BaseSettings


class AgentConfig(BaseSettings):
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_pass: str = "guest"
    rabbitmq_queue: str = "aisoc_alerts"

    ollama_base_url: str = "http://localhost:11434/v1"
    small_llm_model: str = "phi3:mini"
    large_llm_model: str = "llama3.1:8b"

    chroma_host: str = "localhost"
    chroma_port: int = 8000
    chroma_collection: str = "aisoc_playbooks"

    agent_host: str = "0.0.0.0"
    agent_port: int = 8001

    wazuh_api_url: str = "http://localhost:55000"
    wazuh_api_user: str = "wazuh-wui"
    wazuh_api_pass: str = "wazuh-wui"
    wazuh_mock: bool = True

    model_config = {"env_file": ".env", "extra": "ignore"}
