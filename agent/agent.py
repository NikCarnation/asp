import time
from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from agent.categorizer import Categorizer
from agent.models.schemas import AnalysisPlan, IncidentCategory, NormalizedAlert
from agent.planner import Planner
from agent.rag.knowledge_base import CATEGORY_PLAYBOOK_MAP, Playbook
from agent.rag.vector_store import VectorStore

SEP = "─" * 60


class _State(TypedDict):
    alert: NormalizedAlert
    category: Optional[IncidentCategory]
    playbooks: list[Playbook]
    plan: Optional[AnalysisPlan]


def _log(verbose: bool, *args, **kwargs):
    if verbose:
        print(*args, **kwargs)


def _elapsed(start: float) -> str:
    t = time.monotonic() - start
    if t < 60:
        return f"{t:.1f}s"
    return f"{t // 60:.0f}m {t % 60:.0f}s"


def _alert_preview(a: NormalizedAlert) -> str:
    return (
        f"  Rule: {a.rule_name} (level={a.rule_level})\n"
        f"  Source: {a.source_ip or 'N/A'} → {a.destination_ip or 'N/A'}\n"
        f"  Message: {a.message[:200]}"
    )


def create_agent(
    categorizer: Categorizer,
    planner: Planner,
    vector_store: VectorStore,
    verbose: bool = False,
):
    async def categorize_node(state: _State) -> dict:
        t0 = time.monotonic()
        alert = state["alert"]
        _log(verbose, f"\n{SEP}")
        _log(verbose, "  STAGE 1: CATEGORIZER")
        _log(verbose, SEP)
        _log(verbose, "  Input alert:")
        _log(verbose, _alert_preview(alert))

        category = await categorizer.categorize(alert)

        _log(verbose, f"\n  Output category:")
        _log(verbose, f"    category: {category.category} (confidence: {category.confidence})")
        _log(verbose, f"    description: {category.description}")
        _log(verbose, f"  ⏱  {_elapsed(t0)}")
        _log(verbose, SEP)
        return {"category": category}

    async def retrieve_node(state: _State) -> dict:
        t0 = time.monotonic()
        cat = state["category"]
        alert = state["alert"]

        _log(verbose, f"\n{SEP}")
        _log(verbose, "  STAGE 2: RAG (Knowledge Base)")
        _log(verbose, SEP)
        _log(verbose, f"  Query: category={cat.category}, rule={alert.rule_name}")

        playbooks = vector_store.search(category=cat.category, query=alert.rule_name)
        if not playbooks and cat.category in CATEGORY_PLAYBOOK_MAP:
            playbooks = [CATEGORY_PLAYBOOK_MAP[cat.category]]
            _log(verbose, "  Source: fallback (CATEGORY_PLAYBOOK_MAP)")
        elif not playbooks:
            playbooks = vector_store.search(category="unknown", query=alert.rule_name)
            _log(verbose, "  Source: fallback (search 'unknown')")
        else:
            _log(verbose, "  Source: Chroma DB")

        _log(verbose, f"  Results: {len(playbooks)} playbook(s) found")
        for pb in playbooks:
            _log(verbose, f"    • {pb.title} ({len(pb.content)} chars)")
        _log(verbose, f"  ⏱  {_elapsed(t0)}")
        _log(verbose, SEP)
        return {"playbooks": playbooks}

    async def plan_node(state: _State) -> dict:
        t0 = time.monotonic()
        cat = state["category"]
        pbs = state["playbooks"]

        _log(verbose, f"\n{SEP}")
        _log(verbose, "  STAGE 3: PLANNER")
        _log(verbose, SEP)
        _log(verbose, f"  Category: {cat.category}")
        _log(verbose, f"  Playbooks: {len(pbs)}")
        _log(verbose, "  Generating plan...")

        plan = await planner.create_plan(
            alert=state["alert"],
            category=cat.category,
            playbooks=pbs,
        )

        _log(verbose, f"\n  ─── RESULT: AnalysisPlan ───")
        _log(verbose, f"  Summary: {plan.summary[:200]}")
        _log(verbose, f"  Steps: {len(plan.steps)}")
        for s in plan.steps:
            _log(verbose, f"    {s.order}. {s.action}")
        _log(verbose, f"  ⏱  {_elapsed(t0)}")
        _log(verbose, SEP)
        return {"plan": plan}

    workflow = StateGraph(_State)
    workflow.add_node("categorize", categorize_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("plan", plan_node)
    workflow.add_edge(START, "categorize")
    workflow.add_edge("categorize", "retrieve")
    workflow.add_edge("retrieve", "plan")
    workflow.add_edge("plan", END)

    return workflow.compile()
