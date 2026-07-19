
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


    app_name: str = "AVTO-hub — личный кабинет"
    secret_key: str = "dev-only-change-me"
    access_token_expire_minutes: int = 60 * 24


    database_url: str = "sqlite+aiosqlite:///./avtohub.db"


    auto_create_tables: bool = True


    admin_email: str = "admin@avto-hub.ru"
    admin_password: str = "admin123"
    admin_name: str = "Менеджер AVTO-hub"


    cors_origins: str = "*"
    public_url: str = "https://lk.avto-hub.online"


    admin_email: str = "admin@avto-hub.ru"
    admin_password: str = "admin123"


    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""


    podpislon_api_key: str = ""
    podpislon_base_url: str = "https://podpislon.ru/integration"


settings = Settings()
