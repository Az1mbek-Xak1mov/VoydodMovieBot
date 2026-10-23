from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    BOT_TOKEN: str
    DATABASE_URL: str
    # Stored raw to avoid pydantic-settings JSON-decoding a complex type;
    # use the admin_ids property for the parsed list.
    ADMIN_IDS: str

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
