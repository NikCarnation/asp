from agent.categorizer import Categorizer
from agent.models.schemas import AnalysisPlan, NormalizedAlert
from agent.planner import Planner
from agent.rag.knowledge_base import CATEGORY_PLAYBOOK_MAP
from agent.rag.vector_store import VectorStore


class AgentPipeline:
    def __init__(self, categorizer: Categorizer, planner: Planner, vector_store: VectorStore):
        self.categorizer = categorizer
        self.planner = planner
        self.vector_store = vector_store

    async def process(self, alert: NormalizedAlert) -> AnalysisPlan:
        step = "categorization"
        try:
            category = await self.categorizer.categorize(alert)
            step = "rag"

            playbooks = self.vector_store.search(
                category=category.category,
                query=alert.rule_name,
            )

            if not playbooks and category.category in CATEGORY_PLAYBOOK_MAP:
                from agent.rag.knowledge_base import Playbook
                playbooks = [CATEGORY_PLAYBOOK_MAP[category.category]]
            elif not playbooks:
                playbooks = self.vector_store.search(category="unknown", query=alert.rule_name)

            step = "planning"
            plan = await self.planner.create_plan(
                alert=alert,
                category=category.category,
                playbooks=playbooks,
            )
            return plan

        except Exception as e:
            return AnalysisPlan(
                alert_id=alert.event_id,
                incident_category=step,
                created_at=alert.timestamp,
                summary=f"Pipeline error at stage '{step}': {e}",
                steps=[],
                raw_markdown=f"# Error\nPipeline failed at **{step}** stage: {e}",
            )
