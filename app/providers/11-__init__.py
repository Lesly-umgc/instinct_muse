from app.config import settings
from app.providers.base import ModelProvider


def get_provider() -> ModelProvider:
    """Return the configured model provider. Add new providers here."""
    if settings.model_provider == "opencode_zen":
        from app.providers.opencode_zen import OpenCodeZenProvider

        return OpenCodeZenProvider(
            api_key=settings.opencode_api_key,
            base_url=settings.opencode_base_url,
            model=settings.model,
        )
    raise ValueError(f"Unknown MODEL_PROVIDER: {settings.model_provider}")
