"""Settings from environment variables and backend/.env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://trackmymoney:trackmymoney@127.0.0.1:5433/trackmymoney"
    test_database_url: str = "postgresql+psycopg://trackmymoney:trackmymoney@127.0.0.1:5433/trackmymoney_test"
    typesafe_api_key: str = ""  # optional server-side Jev key; the UI can send its own
    cors_origins: str = ""  # comma-separated, for a frontend hosted on another origin
    max_upload_mb: int = 20

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
