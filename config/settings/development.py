from .base import *

DEBUG = True

INSTALLED_APPS = INSTALLED_APPS + ["django_extensions"]

SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-dev-secret-key-do-not-use-in-production")

ALLOWED_HOSTS = ["*"]

CORS_ALLOW_ALL_ORIGINS = True

# SQLite for local dev without Docker (override with env vars for PostgreSQL)
if not os.environ.get("DB_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# In-memory channel layer for local dev without Redis
if not os.environ.get("REDIS_URL"):
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        },
    }

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

INTERNAL_IPS = ["127.0.0.1"]

REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
    "anon": "1000/hour",
    "user": "10000/hour",
    "game_join": "1000/minute",
}