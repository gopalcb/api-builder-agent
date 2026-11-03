"""Migrate project ownership and validate user-scoped UI configuration context."""

from flask import g, request
from sqlalchemy import inspect, select
from werkzeug.exceptions import BadRequest

from models import EntityName, Project, ProjectArchive, ProjectEntityName, ProjectRbacConfiguration, RbacConfiguration, db
from services.user_service import create_user

from services.logger_service import log_function, log_event, LogStep


@log_function
def initialize_projects() -> None:
    """Preserve legacy SQLite workspaces under a separate, unclaimed anonymous user."""
    columns = {column["name"] for column in inspect(db.engine).get_columns("project")}

    if "user_id" not in columns:
        if db.engine.dialect.name != "sqlite":
            raise RuntimeError("Legacy project ownership migration requires SQLite.")

        user = create_user()
        owner = user.id
        db.session.remove()

        with db.engine.connect() as connection:
            foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()

            try:
                with connection.begin():
                    connection.exec_driver_sql(
                        "CREATE TABLE project_owned (id INTEGER PRIMARY KEY, user_id VARCHAR(9) NOT NULL "
                        "REFERENCES users(id), name VARCHAR(100) COLLATE NOCASE NOT NULL, "
                        "summary TEXT NOT NULL, UNIQUE(user_id, name))"
                    )
                    connection.exec_driver_sql(
                        "INSERT INTO project_owned (id, user_id, name, summary) SELECT id, ?, name, summary FROM project", (owner,)
                    )
                    connection.exec_driver_sql("DROP TABLE project")
                    connection.exec_driver_sql("ALTER TABLE project_owned RENAME TO project")
                    connection.exec_driver_sql("CREATE INDEX ix_project_user_id ON project (user_id)")
            finally:
                connection.exec_driver_sql(f"PRAGMA foreign_keys={int(foreign_keys)}")

    if db.session.scalar(select(Project.id).limit(1)) is not None:
        return

    entities = list(db.session.scalars(select(EntityName)))
    legacy = db.session.get(RbacConfiguration, 1)

    if not entities and legacy is None:
        return

    user = create_user()
    project = Project(user_id=user.id, name="Default", summary="Preserved legacy API configuration.")
    db.session.add(project)
    db.session.flush()

    for entity in entities:
        db.session.add(ProjectEntityName(project_id=project.id, name=entity.name))

    if legacy:
        db.session.add(ProjectRbacConfiguration(project_id=project.id, revision=legacy.revision, document=legacy.document))

    db.session.commit()


@log_function
def require_project() -> None:
    """Reject missing, archived, or another user's project context."""
    value = request.headers.get("X-Project-ID", "")

    if not value.isascii() or not value.isdecimal() or len(value) > 10:
        raise BadRequest("Select an active project first.")

    project = db.session.get(Project, int(value))

    if project is None or project.user_id != g.user_id or db.session.get(ProjectArchive, project.id):
        raise BadRequest("The selected project does not exist. Select an active project.")

    g.project_id = project.id
