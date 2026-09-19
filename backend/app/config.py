"""Application settings loaded from environment variables / .env file."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Core
    app_env: str = "development"
    secret_key: str = "change-me"
    access_token_expire_minutes: int = 10080
    database_url: str = "sqlite:///./heard.db"
    cors_origins: str = "http://localhost:5173"

    # Supabase (validate user tokens via the Auth server — no legacy JWT secret needed)
    supabase_url: str = ""
    supabase_publishable_key: str = ""

    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"

    # ElevenLabs
    elevenlabs_api_key: str = ""
    elevenlabs_stt_model: str = "scribe_v1"
    # Realtime (streaming) speech-to-text used by the extension side panel.
    elevenlabs_realtime_model: str = "scribe_v2_realtime"
    elevenlabs_stt_ws_url: str = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"

    # Backboard (stateful coaching layer around Gemini)
    backboard_api_key: str = ""
    # Current Backboard API base URL (used by the raw-HTTP helpers; the SDK
    # manages its own base URL internally).
    backboard_base_url: str = "https://app.backboard.io/api"
    # Which Google/Gemini model Backboard routes coaching through. Query the
    # live list with `GET /models/provider/google` (see backboard.list_google_models)
    # and override via BACKBOARD_GOOGLE_MODEL in .env.
    backboard_google_model: str = "gemini-2.5-flash"

    # TigerTable
    tigertable_api_key: str = ""
    tigertable_base_url: str = "https://api.tigertable.com"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
