import json

from openai import AsyncOpenAI

from agent.models.schemas import IncidentCategory, NormalizedAlert

CATEGORIZE_SYSTEM_PROMPT = """You are an AI SOC analyst. Your task is to categorize security alerts into incident types.

Analyze the alert data and determine the most likely incident category. Return ONLY a JSON object with:
- "category": one of [brute-force, web-exploit, malware, phishing, reconnaissance, unauthorized-access, data-exfiltration, denial-of-service, policy-violation, unknown]
- "confidence": float between 0.0 and 1.0
- "description": brief explanation of your reasoning

Respond with raw JSON only, no markdown formatting."""


class Categorizer:
    def __init__(self, base_url: str, model: str):
        self.client = AsyncOpenAI(base_url=base_url, api_key="ollama")
        self.model = model

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
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": CATEGORIZE_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Alert:\n{alert_text}"},
                ],
                temperature=0.1,
                max_tokens=150,
            )
            content = response.choices[0].message.content.strip()
            content = content.removeprefix("```json").removesuffix("```").strip()
            data = json.loads(content)
            return IncidentCategory(
                category=data.get("category", "unknown"),
                confidence=data.get("confidence", 0.0),
                description=data.get("description", ""),
            )
        except Exception as e:
            return IncidentCategory(
                category="unknown",
                confidence=0.0,
                description=f"Failed to categorize: {e}",
            )
