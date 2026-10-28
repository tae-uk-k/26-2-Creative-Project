"""환경변수 설정(01 4장, 13 1장). 앱 전체에서 get_settings()로만 읽는다."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 04_MVP/seelo/.env(Compose와 공용) → backend/.env 순서로 읽는다. 환경변수가 가장 우선.
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore")

    # 앱
    app_env: Literal["dev", "test", "prod"] = "dev"
    app_base_url: str = "http://localhost:8080"
    log_level: str = "INFO"
    sentry_dsn: str | None = None
    fake_externals: bool = False
    fake_map_behavior: Literal["normal", "block", "reflect_delay"] = "normal"

    # DB·큐
    database_url: str
    queue_database_dsn: str

    # 보안
    secret_key: SecretStr
    email_hmac_key: SecretStr
    mail_token_fernet_key: SecretStr = SecretStr("")
    cookie_secure: bool = False
    session_ttl_days: int = 14
    trusted_proxy_ips: str = "127.0.0.1"

    # OAuth
    google_oauth_client_id: str = ""
    google_oauth_client_secret: SecretStr = SecretStr("")
    kakao_oauth_client_id: str = ""
    kakao_oauth_client_secret: SecretStr = SecretStr("")

    # 지도·검색
    google_places_api_key: SecretStr = SecretStr("")
    kakao_rest_api_key: SecretStr = SecretStr("")
    naver_api_key_id: str = ""
    naver_api_key: SecretStr = SecretStr("")
    naver_local_search_url: str = "https://naverapihub.apigw.ntruss.com/search/v1/local"
    name_similarity_threshold: int = 85
    competitor_facts_enabled: bool = True
    website_user_agent: str = "SeeloBot/1.0"

    # AI
    openai_api_key: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")
    openai_measure_model: str = ""
    gemini_measure_model: str = ""
    openai_cheap_model: str = ""
    openai_plan_model: str = ""
    ai_concurrency_per_provider: int = 5
    ai_repeat_count: int = 10
    daily_cost_limit_usd: float = 0.0
    pricing_file: str = "config/pricing.json"
    snapshot_retention_days: int = 30

    # 메일
    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_starttls: bool = False
    mail_from: str = "seelo <no-reply@example.com>"
    admin_notify_emails: str = ""

    # 정비
    auto_fix_enabled: bool = False
    google_fix_mode: Literal["browser", "api"] = "browser"
    kakao_fix_enabled: bool = True
    gbp_oauth_client_id: str = ""
    gbp_oauth_client_secret: SecretStr = SecretStr("")
    gbp_oauth_refresh_token: SecretStr = SecretStr("")
    gbp_validate_only: bool = False
    browser_profile_dir_google: str = "/data/browser/google"
    browser_profile_dir_kakao: str = "/data/browser/kakao"
    browser_headless: bool = True
    seelo_google_account_email: str = ""
    seelo_kakao_account_id: str = ""

    # 인스타그램
    instagram_business_discovery_enabled: bool = False
    instagram_graph_token: SecretStr = SecretStr("")
    instagram_business_account_id: str = ""
    instagram_graph_version: str = ""

    @property
    def admin_emails(self) -> list[str]:
        return [e.strip() for e in self.admin_notify_emails.split(",") if e.strip()]

    @model_validator(mode="after")
    def _prod_guard(self) -> "Settings":
        if self.app_env == "prod":
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in prod")
            if self.fake_externals:
                raise ValueError("FAKE_EXTERNALS must be false in prod")
            if not self.app_base_url.startswith("https://"):
                raise ValueError("APP_BASE_URL must be https in prod")
            if not self.mail_token_fernet_key.get_secret_value():
                raise ValueError("MAIL_TOKEN_FERNET_KEY must be set in prod")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
