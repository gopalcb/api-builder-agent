"""Persist project cache policies and render reviewed, deterministic integration templates."""

from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

from flask import g
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from models import ProjectCachingConfiguration, db

from services.logger_service import log_function, log_event, LogStep

TEMPLATES = Path(__file__).resolve().parents[2] / "builder-resources/templates/caching"


class CachingError(Exception):
    """Represent a safe cache configuration conflict or missing revision."""

    def __init__(self, message: str, status: int = 409) -> None:
        """Attach an HTTP status to a user-readable error."""
        super().__init__(message)
        self.status = status


@log_function
def read_caching() -> dict:
    """Return the selected project's snapshot and predefined choices."""
    row = db.session.get(ProjectCachingConfiguration, g.project_id)

    return {
        "revision": row.revision if row else 0,
        "configuration": row.document if row else None,
        "presets": json.loads((TEMPLATES / "presets.json").read_text()),
    }


@log_function
def save_caching(configuration: dict, revision: int) -> dict:
    """Save atomically without replacing another editor's revision."""
    if revision == 0:
        db.session.add(ProjectCachingConfiguration(project_id=g.project_id, revision=1, document=configuration))
    else:
        result = db.session.execute(update(ProjectCachingConfiguration).where(
            ProjectCachingConfiguration.project_id == g.project_id,
            ProjectCachingConfiguration.revision == revision,
        ).values(revision=revision + 1, document=configuration))

        if result.rowcount != 1:
            raise CachingError("Configuration changed. Reload the saved version before saving.")

    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise CachingError("Configuration changed. Reload before saving.") from error

    return read_caching()


@log_function
def export_caching(revision: int) -> BytesIO:
    """Export the exact saved revision without provisioning a cache."""
    saved = read_caching()

    if saved["revision"] != revision:
        raise CachingError("Configuration changed. Reload before exporting.")

    if saved["configuration"] is None:
        raise CachingError("Save a configuration before exporting.", 400)

    config = {**saved["configuration"], "namespace": f"project-{g.project_id}:revision-{revision}"}
    files = ["README.md", "gateway.py"] if config["kind"] == "gateway" else ["README.md", "route_cache.py", "example.py"]

    if config["kind"] == "redis":
        files.append("redis_cache.py")

    archive = BytesIO()

    with ZipFile(archive, "w") as bundle:
        bundle.writestr("cache-policy.json", json.dumps(config, indent=2) + "\n")
        dependencies = "aws-cdk-lib==2.273.0\nconstructs==10.5.0\n" if config["kind"] == "gateway" else "Flask>=3.1,<4\n"

        if config["kind"] == "redis":
            dependencies += "redis>=5,<8\n"

        bundle.writestr("requirements.txt", dependencies)

        for filename in files:
            bundle.writestr(filename, (TEMPLATES / filename).read_text())

    archive.seek(0)

    return archive
