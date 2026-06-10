from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABRICKS_HOST: str
    DATABRICKS_TOKEN: str
    GROQ_API_KEY: str
    GROQ_API_KEY_DOCS: str   # separate key for markdown wiki generation

    class Config:
        env_file = ".env"


settings = Settings()