"""Allocate anonymous users and persist their identity in a browser cookie."""

import secrets

from flask import g, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import ServiceUnavailable

from models import Project, User, db

from services.logger_service import log_function, log_event, LogStep

COOKIE_NAME = "user_id"
COOKIE_MAX_AGE = 365 * 24 * 60 * 60


@log_function
def create_user() -> User:
    """Allocate an unused four-digit ID, retrying concurrent allocation conflicts."""
    while True:
        used = set(db.session.scalars(select(User.id)))
        available = [f"user-{number}" for number in range(1000, 10000) if f"user-{number}" not in used]

        if not available:
            raise ServiceUnavailable("Anonymous user capacity reached.")

        user_id = secrets.choice(available)
        user = User(id=user_id, username=user_id, email="", password="")
        db.session.add(user)

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            continue

        return user


@log_function
def bind_user() -> None:
    """Reuse the saved user or create an independent anonymous workspace."""
    user_id = request.cookies.get(COOKIE_NAME)
    user = db.session.get(User, user_id) if user_id else None

    if user is None:
        user = create_user()
        db.session.add(Project(user_id=user.id, name="Default", summary="Default project for your API configuration."))
        db.session.commit()

    g.user_id = user.id


@log_function
def save_user_cookie(response):
    """Persist the invisible identity and prevent caching another user's catalog."""
    if hasattr(g, "user_id"):
        response.set_cookie(COOKIE_NAME, g.user_id, max_age=COOKIE_MAX_AGE,
                            httponly=True, secure=request.is_secure, samesite="Lax", path="/")
        response.headers["Cache-Control"] = "private, no-store"
        response.vary.add("Cookie")

    return response
