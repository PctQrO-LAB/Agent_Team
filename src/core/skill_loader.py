import os
from pathlib import Path
from typing import Iterable, List

from agentscope.tool import Toolkit


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SKILL_ROOT = PROJECT_ROOT / "skills"


def _discover_skill_dirs(base_path: Path) -> List[Path]:
    """
    Return directories that contain a SKILL.md. Handles a direct skill folder
    or a parent directory that holds multiple skill folders.
    """
    dirs: List[Path] = []

    if base_path.is_file():
        return dirs

    skill_file = base_path / "SKILL.md"
    if skill_file.exists():
        dirs.append(base_path)
        return dirs

    if base_path.is_dir():
        for child in base_path.iterdir():
            if child.is_dir() and (child / "SKILL.md").exists():
                dirs.append(child)

    return dirs


def register_agent_skills(toolkit: Toolkit, skill_paths: Iterable[os.PathLike]) -> List[str]:
    """Register AgentScope skills for the given paths and return registered names."""
    registered: List[str] = []

    for path_like in skill_paths:
        base_path = Path(path_like).expanduser()
        if not base_path.is_absolute():
            base_path = PROJECT_ROOT / base_path

        if not base_path.exists():
            print(f"⚠️ Skill path not found: {base_path}")
            continue

        for skill_dir in _discover_skill_dirs(base_path):
            try:
                toolkit.register_agent_skill(str(skill_dir))
                registered.append(skill_dir.name)
                print(f"✅ Registered agent skill: {skill_dir.name} ({skill_dir})")
            except Exception as exc:
                print(f"⚠️ Failed to register skill at {skill_dir}: {exc}")

    return registered


def register_agent_skills_from_env(toolkit: Toolkit, env_var: str = "AGENT_SKILL_DIRS") -> List[str]:
    """
    Read skill directories from an env var (comma-separated). If empty, use
    the default skills/ folder. Returns the names registered.
    """
    raw_value = os.environ.get(env_var, "")

    if raw_value.strip():
        candidates = [part.strip() for part in raw_value.split(",") if part.strip()]
    else:
        candidates = [DEFAULT_SKILL_ROOT]

    return register_agent_skills(toolkit, candidates)
