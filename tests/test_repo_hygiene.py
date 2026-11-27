from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_GITIGNORE_PATTERNS = {
    ".env",
    ".env.*",
    ".vercel/",
    "agy-*.log",
    "*-stream.jsonl",
    "node_modules/",
    "web/node_modules/",
    "web/dist/",
    ".venv/",
    "__pycache__/",
    "*.pyc",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".import_linter_cache/",
    ".DS_Store",
}


def _extract_top_level_yaml_block(yaml_text: str, key: str) -> list[str]:
    lines = yaml_text.splitlines()
    prefix = f"{key}:"
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line[0].isspace() and line.startswith(prefix):
            block: list[str] = []
            rest = line[len(prefix) :].strip()
            if rest:
                block.append(rest)
            for subline in lines[idx + 1 :]:
                sub_stripped = subline.strip()
                if not sub_stripped or sub_stripped.startswith("#"):
                    continue
                if not subline[0].isspace():
                    break
                block.append(sub_stripped)
            return block
    return []


def test_gitignore_contains_required_patterns() -> None:
    gitignore_path = REPO_ROOT / ".gitignore"
    entries = {
        line.strip()
        for line in gitignore_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    missing = sorted(REQUIRED_GITIGNORE_PATTERNS - entries)
    assert not missing, f"Padrões obrigatórios ausentes no .gitignore: {missing}"


def test_ci_workflow_enforces_least_privilege_and_timeout() -> None:
    ci_text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    permissions_block = _extract_top_level_yaml_block(ci_text, "permissions")
    assert permissions_block, "ci.yml deve definir bloco top-level 'permissions'"
    assert any(
        re.fullmatch(r"contents:\s*read", entry) for entry in permissions_block
    ), f"ci.yml deve restringir permissions para 'contents: read', encontrado: {permissions_block}"

    jobs_block = _extract_top_level_yaml_block(ci_text, "jobs")
    assert any(
        re.fullmatch(r"timeout-minutes:\s*[1-9]\d*", entry) for entry in jobs_block
    ), "ci.yml deve definir 'timeout-minutes' positivo no job"
    assert any(
        re.fullmatch(r"run:\s*make setup", entry) for entry in jobs_block
    ), "ci.yml deve executar 'make setup'"


def test_makefile_uses_locked_uv_sync() -> None:
    makefile_lines = (REPO_ROOT / "Makefile").read_text(encoding="utf-8").splitlines()
    uv_sync_lines = [
        line.strip()
        for line in makefile_lines
        if not line.strip().startswith("#") and "uv sync" in line
    ]
    assert uv_sync_lines, "Makefile deve conter comando 'uv sync'"
    unlocked = [line for line in uv_sync_lines if "--locked" not in line.split()]
    assert not unlocked, f"Comandos 'uv sync' sem '--locked' no Makefile: {unlocked}"
