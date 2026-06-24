from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


class Settings(BaseSettings):
    garden_lat: float = 52.2297
    garden_lon: float = 21.0122
    garden_name: str = "Mój ogród"

    hydrawise_api_key: str | None = None

    ha_base_url: str | None = None
    ha_long_lived_token: str | None = None
    ha_mower_entity_id: str | None = None

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"

    poll_interval_minutes: int = 5

    data_dir: Path = ROOT_DIR / "data"
    photos_dir: Path = ROOT_DIR / "data" / "photos"
    maps_dir: Path = ROOT_DIR / "data" / "maps"
    db_path: Path = ROOT_DIR / "data" / "ogrodnik.db"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.photos_dir.mkdir(parents=True, exist_ok=True)
settings.maps_dir.mkdir(parents=True, exist_ok=True)
