import time

from agent.agent import create_agent
from agent.categorizer import Categorizer
from agent.db import save_analysis
from agent.models.schemas import AnalysisPlan, NormalizedAlert
from agent.planner import Planner
from agent.rag.vector_store import VectorStore

SEP = "═" * 60


class AgentPipeline:
    def __init__(
        self,
        categorizer: Categorizer,
        planner: Planner,
        vector_store: VectorStore,
        db_path: str | None = None,
        verbose: bool = False,
    ):
        self.verbose = verbose
        self.db_path = db_path
        self.graph = create_agent(categorizer, planner, vector_store, verbose=verbose)

    async def process(self, alert: NormalizedAlert) -> AnalysisPlan:
        t0 = time.monotonic()
        result = await self.graph.ainvoke({
            "alert": alert,
            "category": None,
            "playbooks": [],
            "plan": None,
        })
        plan = result["plan"]
        duration = time.monotonic() - t0

        if self.verbose:
            print(f"\n{SEP}")
            print(f"  TOTAL: {plan.alert_id} — {plan.incident_category}")
            print(f"  ⏱  {duration:.1f}s total")
            print(f"{SEP}\n")

        if self.db_path:
            cat = result.get("category")
            pbs = result.get("playbooks", [])
            try:
                save_analysis(
                    self.db_path,
                    alert_id=alert.event_id,
                    category=cat.category if cat else "unknown",
                    confidence=cat.confidence if cat else 0.0,
                    category_description=cat.description if cat else "",
                    playbook_titles=[pb.title for pb in pbs],
                    plan_summary=plan.summary,
                    steps_count=len(plan.steps),
                    raw_markdown=plan.raw_markdown,
                    duration_seconds=duration,
                )
            except Exception as e:
                print(f"  [db] save error: {e}")

        return plan
