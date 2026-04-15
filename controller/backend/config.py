from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """Application settings"""
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    recordings_path: Path = Path("./recordings")
    max_cameras: int = 4
    depth_width: int = 640
    depth_height: int = 576
    color_width: int = 1920
    color_height: int = 1080
    fps: int = 30
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

# Ensure recordings directory exists
settings.recordings_path.mkdir(parents=True, exist_ok=True)

