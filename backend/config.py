from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/app.db"
    chroma_path: str = "./data/chroma"
    upload_dir: str = "./uploads"

    # Local LLM settings (llama-cpp-python)
    llm_model_path: str = "./models/microsoft_Phi-4-mini-instruct-Q4_K_M.gguf"
    llm_n_ctx: int = 8192
    llm_n_threads: int = 4
    llm_n_gpu_layers: int = 0      # 0 = CPU only, -1 = all on GPU
    llm_temperature: float = 0.0
    llm_max_tokens: int = 2048

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
