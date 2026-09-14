import os
from typing import List, Optional
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False
    )

    # Core Application Settings
    PROJECT_NAME: str = "Vetra AI Technical Interviewer Platform"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = Field(
        default="vetra_super_secret_jwt_key_change_in_production_2026",
        description="Secret key for security signing and JWTs"
    )
    CORS_ORIGIN: str = Field(
        default="http://localhost:5173",
        description="Allowed CORS origin URL for Frontend interaction"
    )

    @model_validator(mode="before")
    @classmethod
    def handle_cors_origin_alias(cls, values: dict) -> dict:
        if isinstance(values, dict):
            val = values.get("CORS_ORIGIN") or values.get("cors_origin") or values.get("CORS_ORIGINS") or values.get("cors_origins")
            if val is not None:
                if isinstance(val, list):
                    values["CORS_ORIGIN"] = ",".join(val)
                else:
                    values["CORS_ORIGIN"] = str(val)
        return values

    @property
    def CORS_ORIGINS(self) -> List[str]:
        if not self.CORS_ORIGIN:
            return ["*"]
        cleaned = self.CORS_ORIGIN.strip("[]'\" ")
        return [origin.strip().strip("'\"") for origin in cleaned.split(",") if origin.strip()]


    # Supabase & Database Configuration
    SUPABASE_URL: str = Field(default="", description="Supabase project endpoint URL")
    SUPABASE_KEY: str = Field(default="", description="Supabase Anon API key")

    # AI & LLM Service Credentials
    GOOGLE_API_KEY: str = Field(default="", description="Google Gemini API Key for Gemini Live speech-to-speech")
    MOONSHOT_API_KEY: str = Field(default="", description="Moonshot Kimi API Key")


    # Model Selection & Rate Limit Gapping
    GEMINI_REALTIME_MODEL: str = Field(
        default="gemini-3.1-flash-live-preview",
        description="Realtime Voice model used by the Interviewer"
    )
    GEMINI_FLASH_LITE_MODEL: str = Field(
        default="gemini-2.5-flash-lite",
        description="Fast and economical Gemini Flash-Lite model for structured extraction, blueprint, and rubrics"
    )
    GEMINI_PLANNER_MODEL: str = Field(
        default="gemini-2.5-flash",
        description="Gemini Flash model for question generation and exercises"
    )
    EVALUATION_MODEL: str = Field(
        default="gemini-2.5-flash",
        description="LLM Judge model used for post-interview evaluation pipeline"
    )
    MOONSHOT_BASE_URL: str = Field(
        default="https://api.moonshot.ai/v1",
        description="Base URL for Moonshot Kimi API endpoint"
    )
    KIMI_EXERCISE_MODEL: str = Field(
        default="kimi-k2.6",
        description="Kimi model used for dynamic multi-file coding exercise generation"
    )
    ENABLE_KIMI_CODING_FALLBACK: bool = Field(
        default=False,
        description="Explicit gate to allow Kimi AI fallback exclusively for multi-file coding exercise generation"
    )
    KIMI_TIMEOUT_SECONDS: float = Field(
        default=75.0,
        description="Timeout in seconds for Moonshot Kimi API requests"
    )
    KIMI_MAX_RETRIES: int = Field(
        default=2,
        description="Maximum retry attempts on Moonshot Kimi API calls"
    )
    GEMINI_CALL_GAP_SECONDS: float = Field(
        default=2.0,
        description="Delay gap in seconds between sequential Gemini API calls to avoid rate limits"
    )
    GEMINI_MAX_RETRIES: int = Field(
        default=3,
        description="Maximum retry attempts on rate-limited Gemini calls"
    )
    GEMINI_THINKING_BUDGET: int = Field(
        default=0,
        description="Thinking token budget for Gemini models (0 disables thinking for fast structured JSON generation)"
    )

    # Redis & Async Task Workers
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URI for session state and code sync debouncing"
    )

    # Interview Orchestrator & Room Settings
    ROOM_CODE_LENGTH: int = Field(default=6, description="Length of the 6-digit access code for interview rooms")
    CODE_DEBOUNCE_MS: int = Field(default=1500, description="Debounce buffer time in milliseconds for code editor sync")
    MAX_SESSION_DURATION_MINUTES: int = Field(default=60, description="Maximum length of an interview session in minutes")


# Export default singleton instance
settings = Settings()

