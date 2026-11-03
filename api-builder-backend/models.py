"""SQLAlchemy metadata models for entities, attributes, and directed relationships."""

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class EntityName(db.Model):
    """Persist only the ID and name used by the entity configuration screen."""

    __tablename__ = "entities"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100, collation="NOCASE"), nullable=False, unique=True)


class Entity(db.Model):
    """An entity definition with a revision for concurrent generation protection."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=False, default="")
    revision = db.Column(db.Integer, nullable=False, default=0)
    attributes = db.relationship("EntityAttribute", cascade="all, delete-orphan", order_by="EntityAttribute.id")
    relationships = db.relationship(
        "EntityRelationship", foreign_keys="EntityRelationship.entity_id",
        cascade="all, delete-orphan", order_by="EntityRelationship.id",
    )

    def to_dict(self) -> dict:
        """Serialize the persisted definition for API responses and agent context."""
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "revision": self.revision,
            "attributes": [item.to_dict() for item in self.attributes],
            "relationships": [item.to_dict() for item in self.relationships],
        }


class EntityAttribute(db.Model):
    """A named attribute belonging to an entity definition."""

    __table_args__ = (db.UniqueConstraint("entity_id", "name"),)
    id = db.Column(db.Integer, primary_key=True)
    entity_id = db.Column(db.Integer, db.ForeignKey("entity.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    data_type = db.Column(db.String(30), nullable=False)
    nullable = db.Column(db.Boolean, nullable=False)
    description = db.Column(db.Text, nullable=False)

    def to_dict(self) -> dict:
        """Return the schema fields without internal row IDs."""
        return {key: getattr(self, key) for key in ("name", "data_type", "nullable", "description")}


class EntityRelationship(db.Model):
    """A named outgoing relationship referencing an existing target entity."""

    __table_args__ = (db.UniqueConstraint("entity_id", "name"),)
    id = db.Column(db.Integer, primary_key=True)
    entity_id = db.Column(db.Integer, db.ForeignKey("entity.id"), nullable=False)
    target_entity_id = db.Column(db.Integer, db.ForeignKey("entity.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    relationship_type = db.Column(db.String(30), nullable=False)
    description = db.Column(db.Text, nullable=False)

    def to_dict(self) -> dict:
        """Return the target and cardinality of this relationship."""
        return {key: getattr(self, key) for key in (
            "name", "target_entity_id", "relationship_type", "description",
        )}


class RbacConfiguration(db.Model):
    """Persist one local workspace's reviewed RBAC snapshot with optimistic locking."""

    id = db.Column(db.Integer, primary_key=True)
    revision = db.Column(db.Integer, nullable=False)
    document = db.Column(db.JSON, nullable=False)


class User(db.Model):
    """Store anonymous identities without implementing credentials or login."""

    __tablename__ = "users"
    id = db.Column(db.String(9), primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    email = db.Column(db.String(250), nullable=False, default="")
    password = db.Column(db.String(250), nullable=False, default="")


class Project(db.Model):
    """A named configuration workspace selected by the builder UI."""

    __table_args__ = (db.UniqueConstraint("user_id", "name"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(9), db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(100, collation="NOCASE"), nullable=False)
    summary = db.Column(db.Text, nullable=False)

    def to_dict(self) -> dict:
        """Serialize the project card."""
        return {"id": self.id, "name": self.name, "summary": self.summary}


class ProjectEntityName(db.Model):
    """Scope UI entity names without rewriting legacy generation identities."""

    __table_args__ = (db.UniqueConstraint("project_id", "name"),)
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    name = db.Column(db.String(100, collation="NOCASE"), nullable=False)


class ProjectRbacConfiguration(db.Model):
    """One independently versioned RBAC snapshot per project."""

    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), primary_key=True)
    revision = db.Column(db.Integer, nullable=False)
    document = db.Column(db.JSON, nullable=False)


class ProjectCachingConfiguration(db.Model):
    """Keep a revisioned cache policy in its selected project."""

    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), primary_key=True)
    revision = db.Column(db.Integer, nullable=False)
    document = db.Column(db.JSON, nullable=False)


class ProjectDocument(db.Model):
    """Persist edited generated Markdown separately from source configuration."""

    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), primary_key=True)
    slug = db.Column(db.String(100), primary_key=True)
    content = db.Column(db.Text, nullable=False)
    revision = db.Column(db.Integer, nullable=False)


class ProjectArchive(db.Model):
    """Hide deleted projects while retaining their configuration for recovery."""

    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), primary_key=True)


class ProjectBuild(db.Model):
    """Store the exact tested starter bundle and its source fingerprint."""

    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), primary_key=True)
    fingerprint = db.Column(db.String(64), nullable=False)
    archive = db.Column(db.LargeBinary, nullable=False)
    filename = db.Column(db.String(150), nullable=False)


class ProjectRepository(db.Model):
    """Remember a repository destination, never its authentication token."""

    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), primary_key=True)
    owner = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(250), nullable=False)


class ProjectEntityDefinition(db.Model):
    """Persist generated schema separately from the existing entity name catalog."""

    entity_id = db.Column(db.Integer, db.ForeignKey("project_entity_name.id"), primary_key=True)
    revision = db.Column(db.Integer, nullable=False, default=0)
    prompt = db.Column(db.Text, nullable=False, default="")
    document = db.Column(db.JSON, nullable=False)


class ProjectEndpoints(db.Model):
    """Persist the complete reviewed endpoint catalog with optimistic locking."""

    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), primary_key=True)
    revision = db.Column(db.Integer, nullable=False, default=0)
    document = db.Column(db.JSON, nullable=False)


class ProjectObservabilityConfiguration(db.Model):
    """Keep tracing configuration independently revisioned and project-owned."""

    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), primary_key=True)
    revision = db.Column(db.Integer, nullable=False)
    document = db.Column(db.JSON, nullable=False)
