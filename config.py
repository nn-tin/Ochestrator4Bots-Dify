import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent


def _mongodb_uri_from_env(database: str) -> str:
    explicit_uri = os.getenv("MONGODB_URI", "").strip()
    if explicit_uri:
        return explicit_uri

    host = os.getenv("MONGODB_HOST", "").strip()
    if not host:
        return "mongodb://localhost:27017"

    port = int(os.getenv("MONGODB_PORT", "27017"))
    if not 1 <= port <= 65535:
        raise RuntimeError("MONGODB_PORT must be between 1 and 65535")

    username = os.getenv("MONGODB_USERNAME", "")
    password = os.getenv("MONGODB_PASSWORD", "")
    if bool(username) != bool(password):
        raise RuntimeError(
            "MONGODB_USERNAME and MONGODB_PASSWORD must be set together"
        )

    credentials = ""
    if username and password:
        credentials = f"{quote_plus(username)}:{quote_plus(password)}@"

    auth_source = quote_plus(os.getenv("MONGODB_AUTH_SOURCE", "admin"))
    return (
        f"mongodb://{credentials}{host}:{port}/{quote_plus(database)}"
        f"?authSource={auth_source}"
    )


@dataclass(frozen=True)
class Settings:
    qwen_base_url: str
    qwen_bearer: str | None
    qwen_model: str
    qwen_max_tokens: int
    qwen_timeout_seconds: float
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "orchestrator"
    mongodb_collection: str = "conversations"
    mongodb_server_selection_timeout_ms: int = 5000

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(PROJECT_ROOT / ".env")
        max_tokens = int(os.getenv("QWEN_MAX_TOKENS", "512"))
        timeout = float(os.getenv("QWEN_TIMEOUT_SECONDS", "30"))
        mongodb_database = os.getenv("MONGODB_DATABASE", "orchestrator")
        mongo_timeout = int(
            os.getenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS", "5000")
        )
        if max_tokens <= 0:
            raise RuntimeError("QWEN_MAX_TOKENS must be positive")
        if timeout <= 0:
            raise RuntimeError("QWEN_TIMEOUT_SECONDS must be positive")
        if mongo_timeout <= 0:
            raise RuntimeError(
                "MONGODB_SERVER_SELECTION_TIMEOUT_MS must be positive"
            )
        return cls(
            qwen_base_url=os.getenv(
                "QWEN_BASE_URL",
                "https://aistudio.motivesfareast.com/ai-api/idp_llm/v1",
            ).rstrip("/"),
            qwen_bearer=os.getenv("QWEN_BEARER"),
            qwen_model=os.getenv("QWEN_MODEL", "qwen36"),
            qwen_max_tokens=max_tokens,
            qwen_timeout_seconds=timeout,
            mongodb_uri=_mongodb_uri_from_env(mongodb_database),
            mongodb_database=mongodb_database,
            mongodb_collection=os.getenv(
                "MONGODB_COLLECTION", "conversations"
            ),
            mongodb_server_selection_timeout_ms=mongo_timeout,
        )
