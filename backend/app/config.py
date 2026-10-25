"""Settings from environment variables and backend/.env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://trackmymoney:trackmymoney@127.0.0.1:5433/trackmymoney"
    test_database_url: str = "postgresql+psycopg://trackmymoney:trackmymoney@127.0.0.1:5433/trackmymoney_test"
    # Jev: the System One model that reads column headers and categorises transactions. The key is
    # the server's own, used when the browser sends none. The endpoint is TypeSafe's cloud unless the
    # last two are set, e.g. Command Code's Provider API: https://api.commandcode.ai/provider and
    # typesafe/jev.
    jev_api_key: str = ""
    jev_base_url: str = ""
    jev_model: str = ""
    cors_origins: str = ""  # comma-separated, for a frontend hosted on another origin
    max_upload_mb: int = 20

    # Laya: the local, open-source Jev-compatible model that categorises transactions (docker-compose.yml).
    laya_base_url: str = "http://127.0.0.1:8100"
    laya_api_key: str = "local-laya-key"
    laya_model: str = ""  # empty: the server's default router
    categorise_workers: int = 4

    # Key for consistent masking tokens ([PERSON_xxxx]); generated on first use. Saved to
    # `masking_secret_file` when set (Docker: a file on a volume), else appended to backend/.env.
    masking_secret: str = ""
    masking_secret_file: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
