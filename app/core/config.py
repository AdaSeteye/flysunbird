from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENV: str = "local"
    APP_NAME: str = "FlySunbird API"
    # Comma-separated origins for CORS (e.g. https://flysunbird.co.tz,https://admin.flysunbird.co.tz). If empty, uses localhost defaults.
    CORS_ORIGINS: str = ""

    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    DATABASE_URL: str

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        """Render and others give postgres://; SQLAlchemy expects postgresql+psycopg2://."""
        if v and v.startswith("postgres://"):
            return "postgresql+psycopg2://" + v[11:]
        return v
    REDIS_URL: str = "redis://localhost:6379/0"

    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 25
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "ops@flysunbird.local"

    SENDGRID_API_KEY: str = ""
    SENDGRID_FROM_EMAIL: str = ""

    CLIENT_BASE_URL: str = ""  # e.g. https://flysunbird.co.tz
    API_PUBLIC_URL: str = ""  # e.g. https://api.flysunbird.co.tz - for ticket QR code (scan → PDF)

    # Ticket storage
    TICKET_LOCAL_DIR: str = "./data/tickets"
    GCS_BUCKET_NAME: str = ""
    GOOGLE_APPLICATION_CREDENTIALS: str = ""

    # Stripe (Checkout redirect)
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""  # For webhook signature verification (e.g. whsec_...)

    # Selcom (Tanzania: mobile money, cards). Vendor = Till Number from Selcom.
    SELCOM_BASE_URL: str = "https://apigw.selcommobile.com/v1"
    SELCOM_API_KEY: str = ""
    SELCOM_API_SECRET: str = ""
    SELCOM_VENDOR: str = ""    # Vendor / Till Number

    # Partners app (PHP): base URL for partner-by-code API (e.g. https://partners.flysunbird.co.tz). Empty = no lookup.
    PARTNERS_APP_URL: str = ""

    # Bootstrap admin (seed): only one admin is created. Set ADMIN_INITIAL_PASSWORD in production.
    ADMIN_EMAIL: str = "admin@flysunbird.co.tz"
    ADMIN_INITIAL_PASSWORD: str = "ChangeMe123!"

    # Bank details for unpaid ticket
    BANK_NAME: str = "CRDB BANK"
    BANK_ACCOUNT_NAME: str = "PREMIER AIR LIMITED"
    BANK_ACCOUNT_USD: str = "0250000WKYA00"
    BANK_ACCOUNT_TZS: str = "0150000WKYA00"
    BANK_BRANCH: str = "Palm Beach, Dar es Salaam, Tanzania"
    BANK_SWIFT: str = "CORUTZTZXXX"


settings = Settings()
