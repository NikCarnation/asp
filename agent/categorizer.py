from langchain_openai import ChatOpenAI

from agent.models.schemas import IncidentCategory, NormalizedAlert
from agent.prompts import CATEGORIZE_SYSTEM_PROMPT


class Categorizer:
    def __init__(self, base_url: str, model: str, api_key: str = ""):
        self.llm = ChatOpenAI(
            base_url=base_url,
            model=model,
            api_key=api_key or "ollama",
            temperature=0.1,
            max_tokens=150,
        ).with_structured_output(IncidentCategory)

    async def categorize(self, alert: NormalizedAlert) -> IncidentCategory:
        alert_text = (
            f"Rule: {alert.rule_name} (id={alert.rule_id}, level={alert.rule_level})\n"
            f"Category: {alert.event_category}\n"
            f"Source: {alert.source_ip}:{alert.source_port}\n"
            f"Destination: {alert.destination_ip}:{alert.destination_port}\n"
            f"User: {alert.user_name}\n"
            f"Process: {alert.process_name}\n"
            f"Protocol: {alert.network_protocol}\n"
            f"Message: {alert.message[:500]}"
        )
        try:
            return await self.llm.ainvoke([
                {"role": "system", "content": CATEGORIZE_SYSTEM_PROMPT},
                {"role": "user", "content": f"Alert:\n{alert_text}"},
            ])
        except Exception as e:
            return IncidentCategory(
                category="unknown",
                confidence=0.0,
                description=f"Failed to categorize: {e}",
            )
