from pydantic_settings import BaseSettings


class AgentConfig(BaseSettings):
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_pass: str = "guest"
    rabbitmq_queue: str = "aisoc_alerts"

    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = ""
    small_llm_model: str = ""
    large_llm_model: str = ""

    chroma_persist_dir: str = "./chroma_data"
    chroma_collection: str = "aisoc_playbooks"
    embedding_model: str = "nomic-embed-text"

    agent_host: str = "0.0.0.0"
    agent_port: int = 8001

    db_path: str = "data/analyses.db"

    verbose: bool = True

    model_config = {"env_file": ".env", "extra": "ignore"}
