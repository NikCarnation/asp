from pathlib import Path

from pydantic import BaseModel


class Playbook(BaseModel):
    title: str
    category: str
    content: str
    source: str | None = None


KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge"


def _load_playbooks() -> list[Playbook]:
    playbooks = []
    if not KNOWLEDGE_DIR.exists():
        return playbooks
    for md_file in sorted(KNOWLEDGE_DIR.glob("*.md")):
        category = md_file.stem
        content = md_file.read_text(encoding="utf-8")
        title = content.split("\n")[0].removeprefix("# ").strip() if content.startswith("#") else category.replace("-", " ").title()
        playbooks.append(Playbook(
            title=title,
            category=category,
            content=content,
            source="AISOC Knowledge Base",
        ))
    return playbooks


ALL_PLAYBOOKS = _load_playbooks()
CATEGORY_PLAYBOOK_MAP: dict[str, Playbook] = {pb.category: pb for pb in ALL_PLAYBOOKS}
