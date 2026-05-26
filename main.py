"""
AISOC - AI Agent System for Information Security Event Analysis

Entry point for orchestrating the full pipeline.
Can run both connector and agent in-process for development,
or delegate to Docker Compose for production.
"""

import asyncio
import os
import signal
import sys

from dotenv import load_dotenv

load_dotenv()

MODE = os.getenv("AISOC_MODE", "help")


def main():
    if MODE == "connector":
        import uvicorn
        from connector.config import ConnectorConfig
        cfg = ConnectorConfig()
        uvicorn.run(
            "connector.main:app",
            host=cfg.connector_host,
            port=cfg.connector_port,
            reload=True,
        )
    elif MODE == "agent":
        import uvicorn
        from agent.config import AgentConfig
        cfg = AgentConfig()
        uvicorn.run(
            "agent.main:app",
            host=cfg.agent_host,
            port=cfg.agent_port,
            reload=True,
        )
    else:
        print("AISOC - AI Agent SOC System")
        print()
        print("Usage:")
        print("  AISOC_MODE=connector python main.py    # Run connector microservice")
        print("  AISOC_MODE=agent python main.py         # Run agent microservice")
        print()
        print("Or use Docker Compose for full deployment:")
        print("  docker compose up --build")


if __name__ == "__main__":
    main()
