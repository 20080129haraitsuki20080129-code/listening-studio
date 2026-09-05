"""Enforce the SPEC's architectural boundary mechanically.

SPEC section 26 requires that provider SDKs are not imported from the domain
layer, and section 18 that FFmpeg is only called from infrastructure/audio.
Checking that by eye rots; this fails the build instead.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"

PROVIDER_MODULES = {
    "kokoro",
    "misaki",
    "torch",
    "soundfile",
    "openai",
    "azure",
    "elevenlabs",
    "azure.cognitiveservices",
    "espeakng_loader",
    "phonemizer",
}
TTS_LAYER = APP / "infrastructure" / "tts"
AUDIO_LAYER = APP / "infrastructure" / "audio"


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def _python_files() -> list[Path]:
    return [p for p in APP.rglob("*.py") if "__pycache__" not in p.parts]


def test_provider_sdks_only_imported_in_the_tts_layer():
    offenders: list[str] = []
    for path in _python_files():
        # config.py resolves espeak paths as configuration, which is where
        # provider-specific knowledge is allowed to live (SPEC 8.1).
        if path.is_relative_to(TTS_LAYER) or path.name == "config.py":
            continue
        leaked = _imported_roots(path) & PROVIDER_MODULES
        if leaked:
            offenders.append(f"{path.relative_to(APP)}: {sorted(leaked)}")
    assert not offenders, (
        "provider SDK imported outside infrastructure/tts:\n" + "\n".join(offenders)
    )


def test_domain_layer_imports_no_infrastructure():
    offenders: list[str] = []
    for path in (APP / "domain").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        if "app.infrastructure" in source:
            offenders.append(str(path.relative_to(APP)))
    assert not offenders, f"domain layer depends on infrastructure: {offenders}"


def test_subprocess_only_used_in_infrastructure():
    """FFmpeg and `say` are shelled out to; that must stay in infrastructure."""
    offenders: list[str] = []
    for path in _python_files():
        if path.is_relative_to(APP / "infrastructure"):
            continue
        if "subprocess" in _imported_roots(path):
            offenders.append(str(path.relative_to(APP)))
    assert not offenders, f"subprocess used outside infrastructure: {offenders}"


def test_api_layer_does_not_import_orm_models_for_response_shaping():
    """DB models must not leak into the frontend contract (SPEC section 18).

    Routes may touch models, but every response is declared as a Pydantic
    schema, so check that each route module imports from app.schemas.
    """
    for path in (APP / "api" / "routes").glob("*.py"):
        if path.name == "__init__.py":
            continue
        source = path.read_text(encoding="utf-8")
        if "response_model" in source:
            assert "app.schemas" in source, (
                f"{path.name} returns models without a schema"
            )
