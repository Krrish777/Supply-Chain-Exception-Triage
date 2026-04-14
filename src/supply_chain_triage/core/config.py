"""Settings + runtime singletons (Secret Manager, Firestore client).

This module is the ONE place in ``core/`` where framework-specific imports
(``google.cloud.firestore``, ``google.cloud.secretmanager``) are allowed. It
is the DI chokepoint for the rest of the codebase:

- Business logic never instantiates a Firestore client; it calls
  :func:`get_firestore_client`.
- Agent tools never call Secret Manager directly; they call :func:`get_secret`.
- Everything else in ``core/`` stays framework-neutral.

If you need to swap Firestore for another persistence layer or Secret Manager
for another secret store, the changes land here and in the concrete adapters
under ``modules/*/memory/`` — not scattered across agents and tools.

Ruff ``TID251`` is waived on this file via ``pyproject.toml``
``[tool.ruff.lint.per-file-ignores]``. Every new framework-specific import added
here should earn its keep — consider a separate adapter first.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import TYPE_CHECKING

from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:  # pragma: no cover
    from google.cloud import firestore


class SecretNotFoundError(Exception):
    """Raised when :func:`get_secret` cannot locate a secret in any backend."""


class Settings(BaseSettings):
    """Application settings populated from environment + `.env` file.

    Prefixes:
    - Plain env vars (``GCP_PROJECT_ID`` etc.) for app settings.
    - ``SCT_SECRET__<KEY>`` for local-dev secret fallbacks (consumed by
      :func:`get_secret`, not read into this model).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    gcp_project_id: str
    firebase_project_id: str
    cors_allowed_origins: list[str] = ["http://localhost:3000"]

    # Emulator toggles. Setting either switches the corresponding client to
    # the emulator. NEVER set FIREBASE_AUTH_EMULATOR_HOST in prod — the Admin
    # SDK will accept forged tokens (see .claude/rules/testing.md §6).
    firestore_emulator_host: str | None = None
    firebase_auth_emulator_host: str | None = None

    # Logging — consumed by utils.logging at configure time. Overriding here
    # via env lets Cloud Run (LOG_TO_FILES=0) and local dev (defaults) share
    # the same binary. See .claude/rules/logging.md §8.
    log_level: str = "INFO"
    log_to_files: bool = True
    logs_dir: str = "logs"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings singleton.

    Cached via ``lru_cache``. Tests can reset the cache via
    ``get_settings.cache_clear()``.
    """
    return Settings()  # type: ignore[call-arg]


def get_secret(key: str) -> str:
    """Return a secret value.

    Resolution order:

    1. ``SCT_SECRET__<KEY>`` environment variable — local dev fallback.
    2. GCP Secret Manager via
       ``projects/<gcp_project_id>/secrets/<key>/versions/latest`` — unless
       ``SCT_DISABLE_SECRET_MANAGER=1``.
    3. :class:`SecretNotFoundError` naming the requested key.

    The env fallback keeps local dev frictionless (drop values in ``.env`` and
    they resolve). The ``SCT_DISABLE_SECRET_MANAGER`` escape hatch is for unit
    tests that want strict isolation from GCP.
    """
    env_key = f"SCT_SECRET__{key}"
    if (env_value := os.environ.get(env_key)) is not None:
        return env_value

    if os.environ.get("SCT_DISABLE_SECRET_MANAGER") == "1":
        raise SecretNotFoundError(
            f"Secret {key!r} not found in env (SCT_DISABLE_SECRET_MANAGER=1 "
            f"prevents Secret Manager lookup)"
        )

    # Lazy import — keeps pytest unit tests fast when secret manager isn't used.
    try:
        from google.cloud import secretmanager
    except ImportError as exc:  # pragma: no cover
        raise SecretNotFoundError(
            f"Secret {key!r} not in env and google-cloud-secret-manager not installed"
        ) from exc

    settings = get_settings()
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{settings.gcp_project_id}/secrets/{key}/versions/latest"
    try:
        response = client.access_secret_version(request={"name": name})
    except Exception as exc:  # broad: surface everything as SecretNotFoundError
        raise SecretNotFoundError(
            f"Secret {key!r} not accessible in GCP Secret Manager: {exc}"
        ) from exc

    return response.payload.data.decode("utf-8")


@lru_cache(maxsize=1)
def get_firestore_client() -> firestore.AsyncClient:
    """Return the process-wide async Firestore client.

    Honors ``FIRESTORE_EMULATOR_HOST`` — if set (either directly via env or
    via the ``firestore_emulator_host`` Setting), the client routes to the
    local emulator rather than prod.

    CR9: Settings' ``firestore_emulator_host`` is exported to the real env var
    before client construction, because the Firestore SDK reads
    ``FIRESTORE_EMULATOR_HOST`` from ``os.environ`` at client-init time. If a
    caller sets the Settings field but forgot to export the env var, this
    factory used to silently talk to prod. Now it doesn't.
    """
    from google.cloud import firestore

    settings = get_settings()
    if settings.firestore_emulator_host and not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        os.environ["FIRESTORE_EMULATOR_HOST"] = settings.firestore_emulator_host
    return firestore.AsyncClient(project=settings.gcp_project_id)
