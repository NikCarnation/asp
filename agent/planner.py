import json
from datetime import datetime, timezone

from openai import AsyncOpenAI

from agent.models.schemas import AnalysisPlan, NormalizedAlert, PlanStep
from agent.rag.knowledge_base import Playbook

PLANNER_SYSTEM_PROMPT = """You are a senior SOC analyst creating an incident investigation plan.

You will receive:
1. A security alert
2. The incident category determined by preliminary analysis
3. Relevant playbook information from the knowledge base

Create a structured investigation plan with specific, actionable steps.

Return a JSON object with the following structure:
{
  "summary": "Brief 1-2 sentence summary of the incident",
  "steps": [
    {
      "order": 1,
      "action": "Short action name",
      "description": "Detailed description of what to do",
      "commands": ["command1", "command2"],
      "expected_result": "What to expect from this step"
    }
  ]
}

Also provide the plan as raw markdown text in a "raw_markdown" field.

Respond with raw JSON only, no markdown formatting."""


class Planner:
    def __init__(self, base_url: str, model: str):
        self.client = AsyncOpenAI(base_url=base_url, api_key="ollama")
        self.model = model

    async def create_plan(
        self,
        alert: NormalizedAlert,
        category: str,
        playbooks: list[Playbook],
    ) -> AnalysisPlan:
        playbook_text = "\n\n---\n\n".join(
            f"## {pb.title}\n{pb.content}" for pb in playbooks
        ) if playbooks else "No specific playbook found for this category. Use general SOC analysis best practices."

        alert_summary = (
            f"Rule: {alert.rule_name} (level={alert.rule_level})\n"
            f"Category: {alert.event_category}\n"
            f"Source: {alert.source_ip or 'N/A'}\n"
            f"Destination: {alert.destination_ip or 'N/A'}\n"
            f"User: {alert.user_name or 'N/A'}\n"
            f"Message: {alert.message[:1000]}"
        )

        user_prompt = (
            f"## Alert\n{alert_summary}\n\n"
            f"## Classified Category\n{category}\n\n"
            f"## Knowledge Base\n{playbook_text}"
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=2000,
            )
            content = response.choices[0].message.content.strip()
            content = content.removeprefix("```json").removesuffix("```").strip()
            data = json.loads(content)

            steps = [
                PlanStep(
                    order=s.get("order", i + 1),
                    action=s.get("action", ""),
                    description=s.get("description", ""),
                    commands=s.get("commands", []),
                    expected_result=s.get("expected_result", ""),
                )
                for i, s in enumerate(data.get("steps", []))
            ]

            return AnalysisPlan(
                alert_id=alert.event_id,
                incident_category=category,
                created_at=datetime.now(timezone.utc),
                summary=data.get("summary", ""),
                steps=steps,
                raw_markdown=data.get("raw_markdown", ""),
            )
        except Exception as e:
            return AnalysisPlan(
                alert_id=alert.event_id,
                incident_category=category,
                created_at=datetime.now(timezone.utc),
                summary=f"Failed to generate plan: {e}",
                steps=[
                    PlanStep(
                        order=1,
                        action="Manual Analysis Required",
                        description=f"Auto-generation failed: {e}. Review alert manually.",
                        commands=[],
                        expected_result="Manual investigation results",
                    )
                ],
                raw_markdown=f"# Analysis Plan: {alert.rule_name}\n\n*Auto-generation failed. Manual analysis required.*",
            )
