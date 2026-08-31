"""
Central configuration for the project.

Everything reads from .env via pydantic-settings. Import `settings` anywhere
you need a config value - never read os.environ directly in other modules.

This project is MOBILE (Android/Appium) ONLY. There is no web/Selenium
target here - the app under test is always the native Android app defined
by ANDROID_APP_PACKAGE / ANDROID_APP_ACTIVITY, launched automatically by
Appium when the driver session starts.
"""

from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    # ---- LLM provider toggle ----
    # ONE switch controls BOTH text (planning/resolving/verifying) and vision
    # calls - "groq" or "azure". There is no separate vision provider anymore:
    #   LLM_PROVIDER=groq  -> GROQ_MODEL for text, GROQ_VISION_MODEL for vision
    #   LLM_PROVIDER=azure -> AZURE_OPENAI_DEPLOYMENT (e.g. your gpt-4.1-mini
    #                         deployment) is used for BOTH text and vision,
    #                         since gpt-4.1-mini is multimodal.
    llm_provider: str = Field("groq", alias="LLM_PROVIDER")  # groq | azure

    # ---- Groq ----
    groq_api_key: Optional[str] = Field(None, alias="GROQ_API_KEY")
    groq_model: str = Field("openai/gpt-oss-20b", alias="GROQ_MODEL")
    groq_vision_model: str = Field("qwen/qwen3.6-27b", alias="GROQ_VISION_MODEL")

    # ---- Azure OpenAI (used for both text and vision when LLM_PROVIDER=azure) ----
    azure_openai_api_key: Optional[str] = Field(None, alias="AZURE_OPENAI_API_KEY")
    azure_openai_endpoint: Optional[str] = Field(None, alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_version: str = Field("2024-08-01-preview", alias="AZURE_OPENAI_API_VERSION")
    # Should point at your gpt-4.1-mini deployment name (not the model name).
    azure_openai_deployment: Optional[str] = Field(None, alias="AZURE_OPENAI_DEPLOYMENT")

    # ---- Appium / Android target ----
    appium_server_url: str = Field("http://127.0.0.1:4723", alias="APPIUM_SERVER_URL")
    android_device_name: str = Field("Android Device", alias="ANDROID_DEVICE_NAME")
    android_app_package: str = Field("", alias="ANDROID_APP_PACKAGE")
    android_app_activity: str = Field("", alias="ANDROID_APP_ACTIVITY")
    android_udid: Optional[str] = Field(None, alias="ANDROID_UDID")
    android_platform_version: Optional[str] = Field(None, alias="ANDROID_PLATFORM_VERSION")
    android_no_reset: bool = Field(True, alias="ANDROID_NO_RESET")
    android_new_command_timeout: int = Field(900, alias="ANDROID_NEW_COMMAND_TIMEOUT")
    android_auto_grant_permissions: bool = Field(True, alias="ANDROID_AUTO_GRANT_PERMISSIONS")

    # ---- Agent behaviour ----
    # Caps how many atomic steps a single plan may contain (safety ceiling on
    # the PLAN, not a per-step retry loop - see planner.py/agent.py).
    max_steps: int = Field(25, alias="MAX_STEPS")
    fuzzy_match_threshold: int = Field(75, alias="FUZZY_MATCH_THRESHOLD")
    enable_vision_fallback: bool = Field(True, alias="ENABLE_VISION_FALLBACK")
    popup_dismiss_enabled: bool = Field(True, alias="POPUP_DISMISS_ENABLED")

    # ---- Paths (not read from env) ----
    base_dir: Path = BASE_DIR
    screenshot_dir: Path = BASE_DIR / "logs" / "screenshots"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )


settings = Settings()
settings.screenshot_dir.mkdir(parents=True, exist_ok=True)
