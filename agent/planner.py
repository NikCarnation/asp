from datetime import datetime, timezone

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from agent.models.schemas import AnalysisPlan, NormalizedAlert, PlanStep
from agent.prompts import PLANNER_SYSTEM_PROMPT
from agent.rag.knowledge_base import Playbook


class _PlanOutput(BaseModel):
    summary: str
    steps: list[PlanStep]
    raw_markdown: str = ""


class Planner:
    def __init__(self, base_url: str, model: str, api_key: str = ""):
        self.llm = ChatOpenAI(
            base_url=base_url,
            model=model,
            api_key=api_key or "ollama",
            temperature=0.2,
            max_tokens=2000,
        ).with_structured_output(_PlanOutput)

    async def create_plan(
        self,
        alert: NormalizedAlert,
        category: str,
        playbooks: list[Playbook],
    ) -> AnalysisPlan:
        playbook_text = "\n\n---\n\n".join(
            f"## {pb.title}\n{pb.content}" for pb in playbooks
        ) if playbooks else "No specific playbook found for this category."

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
            result = await self.llm.ainvoke([
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ])
            return AnalysisPlan(
                alert_id=alert.event_id,
                incident_category=category,
                created_at=datetime.now(timezone.utc),
                summary=result.summary,
                steps=result.steps,
                raw_markdown=result.raw_markdown,
            )
        except Exception as e:
            return AnalysisPlan(
                alert_id=alert.event_id,
                incident_category=category,
                created_at=datetime.now(timezone.utc),
                summary=f"Failed to generate plan: {e}",
                steps=[],
                raw_markdown=f"# Error\nPlan generation failed: {e}",
            )
