"""Build-only module: deliberately independent of the ASGI application."""

from pathlib import Path
from workingtitle.devserver import AssetPlan, NpmBuild

ASSETS = AssetPlan(
    root=Path(__file__).resolve().parent,
    steps=(
        NpmBuild(
            "frontend",
            ("frontend/**", "build.mjs"),
            ("static/index.js", "static/index.css"),
        ),
    ),
)
