from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    app_secret_key: str = "change-me"
    app_pin: str = ""

    strava_client_id: str = ""
    strava_client_secret: str = ""
    strava_redirect_uri: str = "http://localhost:8000/api/auth/strava/callback"

    intervals_api_key: str = ""
    intervals_athlete_id: str = ""

    ai_provider: str = "claude"
    ollama_url: str = "http://localhost:11434"
    ollama_model_light: str = "llama3.1"
    ollama_model_heavy: str = "llama3.1:70b"
    claude_model_light: str = "claude-haiku-4-5-20251001"
    claude_model_heavy: str = "claude-fable-5"
    openai_model_light: str = "gpt-4o-mini"
    openai_model_heavy: str = "gpt-4o"
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    sync_interval: int = 15
    ftp: int = 200
    # Running threshold pace in seconds per km (5:00/km default). Runs are
    # prescribed against this the way rides are prescribed against FTP.
    threshold_pace: int = 300
    # Swim threshold (CSS) pace in seconds per 100m.
    swim_css_pace: int = 105

    database_url: str = "sqlite+aiosqlite:///./data/pulse.db"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
