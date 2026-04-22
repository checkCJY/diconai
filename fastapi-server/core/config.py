from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DRF_BASE_URL: str = "http://localhost:8002"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
