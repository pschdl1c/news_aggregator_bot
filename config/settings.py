from pydantic_settings import BaseSettings, SettingsConfigDict


MODEL_CATALOGUE = [
    {
        "id": "gemini-3.5-flash-lite",
        "tier": "G",
        "input_token_limit": 1048576,
        "output_token_limit": 65536,
    },
    {
        "id": "gemma-4-31b-it",
        "tier": "S",
        "input_token_limit": 131072,
        "output_token_limit": 8192,
    },
    {
        "id": "gemma-4-26b-a4b-it",
        "tier": "A",
        "input_token_limit": 131072,
        "output_token_limit": 8192,
    },
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    google_api_key: str
    admin_user_id: int

    default_model: str = "gemini-3.5-flash-lite"
    database_path: str = "./data/bot.db"
    llm_workflow_log: bool = False


settings = Settings()
