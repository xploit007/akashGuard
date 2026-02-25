from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # AkashML LLM
    akashml_api_key: str = ""
    akashml_base_url: str = "https://api.akashml.com/v1"
    akashml_model: str = "meta-llama/Llama-3.3-70B-Instruct"

    # Akash Console API
    akash_console_api_key: str = ""
    akash_console_api_base: str = "https://console-api.akash.network/v1"

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Langfuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = "https://cloud.langfuse.com"

    # Database
    db_path: str = "./data/akashguard.db"

    # Health check tuning
    health_check_interval: int = 30
    failure_threshold: int = 5
    response_time_threshold_ms: int = 5000

    # Set to true to start the monitoring loop when the API starts.
    # When false, the API serves the dashboard/SSE endpoints but does
    # NOT actively monitor services (useful for dev / frontend-only mode).
    agent_auto_monitor: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
