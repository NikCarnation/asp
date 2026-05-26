import time
from datetime import datetime, timezone

from agent.agent import create_agent
from agent.categorizer import Categorizer
from agent.db import save_analysis
from agent.models.schemas import AnalysisPlan, NormalizedAlert
from agent.planner import Planner
from agent.rag.vector_store import VectorStore
from agent.indexer_client import AgentIndexerClient

SEP = "\u2550" * 60


class AgentPipeline:
    def __init__(
        self,
        categorizer: Categorizer,
        planner: Planner,
        vector_store: VectorStore,
        db_path: str | None = None,
        indexer_client: AgentIndexerClient | None = None,
        verbose: bool = False,
    ):
        self.verbose = verbose
        self.db_path = db_path
        self.indexer_client = indexer_client
        self.graph = create_agent(categorizer, planner, vector_store, verbose=verbose)

    def _build_indexer_doc(self, alert: NormalizedAlert, plan: AnalysisPlan,
                           cat, pbs, duration: float) -> dict:
        return {
            "@timestamp": datetime.now(timezone.utc).isoformat(),
            "event_id": alert.event_id,
            "rule_id": alert.rule_id,
            "rule_name": alert.rule_name,
            "rule_level": alert.rule_level,
            "source_ip": alert.source_ip,
            "destination_ip": alert.destination_ip,
            "user_name": alert.user_name,
            "network_protocol": alert.network_protocol,
            "message": alert.message,
            "aisoc": {
                "alert_id": plan.alert_id,
                "category": cat.category if cat else "unknown",
                "confidence": cat.confidence if cat else 0.0,
                "category_description": cat.description if cat else "",
                "summary": plan.summary,
                "steps_count": len(plan.steps),
                "steps": [s.model_dump() for s in plan.steps],
                "raw_markdown": plan.raw_markdown,
                "duration_seconds": duration,
                "created_at": plan.created_at.isoformat(),
            }
        }

    async def process(self, alert: NormalizedAlert) -> AnalysisPlan:
        t0 = time.monotonic()
        result = await self.graph.ainvoke({
            "alert": alert,
            "category": None,
            "playbooks": [],
            "plan": None,
        })
        plan = result["plan"]
        cat = result.get("category")
        pbs = result.get("playbooks", [])
        duration = time.monotonic() - t0

        if self.verbose:
            print(f"\n{SEP}")
            print(f"  TOTAL: {plan.alert_id} \u2014 {plan.incident_category}")
            print(f"  \u23f1  {duration:.1f}s total")
            print(f"{SEP}\n")

        if self.db_path:
            try:
                save_analysis(
                    self.db_path,
                    alert_id=alert.event_id,
                    raw_alert=alert.raw if alert.raw else None,
                    normalized_alert=alert.model_dump(mode="json"),
                    category=cat.category if cat else "unknown",
                    confidence=cat.confidence if cat else 0.0,
                    category_description=cat.description if cat else "",
                    rag_query=f"category={cat.category if cat else 'unknown'}, rule={alert.rule_name}",
                    rag_playbooks=[pb.title for pb in pbs],
                    plan_result=plan.model_dump(mode="json"),
                    plan_summary=plan.summary,
                    steps_count=len(plan.steps),
                    raw_markdown=plan.raw_markdown,
                    duration_seconds=duration,
                )
            except Exception as e:
                print(f"  [db] save error: {e}")

        if self.indexer_client:
            try:
                doc = self._build_indexer_doc(alert, plan, cat, pbs, duration)
                await self.indexer_client.index_analysis(doc)
            except Exception as e:
                print(f"  [indexer] send error: {e}")

        return plan