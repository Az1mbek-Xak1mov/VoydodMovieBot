from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    BOT_TOKEN: str
    DATABASE_URL: str
    # Stored raw to avoid pydantic-settings JSON-decoding a complex type;
    # use the admin_ids property for the parsed list.
    ADMIN_IDS: str

    # Azure OpenAI image generation/editing (gpt-image-2 deployment).
    AZURE_OPENAI_ENDPOINT_IMAGE: str
    AZURE_OPENAI_API_KEY_IMAGE: str
    AZURE_OPENAI_DEPLOYMENT_IMAGE: str = "gpt-image-2"
    # The Images Edit endpoint requires this version; older ones (e.g.
    # 2024-12-01-preview) return 404 for /images/edits.
    AZURE_OPENAI_API_VERSION: str = "2025-04-01-preview"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def admin_ids(self) -> list[int]:
        """Parse the comma-separated ADMIN_IDS string into a list of ints."""
        return [int(part) for part in self.ADMIN_IDS.split(",") if part.strip()]


settings = Settings()
