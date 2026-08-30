"""Configuration for the FoPost integration, read from ``FOPOST_*`` environment variables."""

from __future__ import annotations

from fopost import DEFAULT_BASE_URL
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["FoPostSettings"]


class FoPostSettings(BaseSettings):
    """Settings for the FoPost client and webhook receiver.

    Every field is read from the matching ``FOPOST_``-prefixed environment
    variable, so ``FOPOST_API_KEY`` fills ``api_key``::

        settings = FoPostSettings()                     # from the environment
        settings = FoPostSettings(api_key="fp_...")     # or explicitly
    """

    model_config = SettingsConfigDict(
        env_prefix="FOPOST_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: str | None = Field(
        default=None,
        description="API key from https://app.fopost.com/api-keys, sent as X-API-Key.",
    )
    base_url: str = Field(
        default=DEFAULT_BASE_URL,
        description="Root of the FoPost API.",
    )
    timeout: float = Field(
        default=30.0,
        gt=0,
        description="Seconds to wait for a single request before giving up.",
    )
    max_retries: int = Field(
        default=3,
        ge=1,
        description="Attempts a rate limited request gets, including the first.",
    )
    default_workspace_id: str | None = Field(
        default=None,
        description="Workspace to fall back to when a route does not name one.",
    )
    webhook_secret: str | None = Field(
        default=None,
        description="Secret of the FoPost webhook whose deliveries this app receives.",
    )
