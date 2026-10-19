from typing import Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.config import get_settings

settings = get_settings()


def get_llm(model: Optional[str] = None, temperature: Optional[float] = None) -> ChatGoogleGenerativeAI:
    """Instantiate a ChatGoogleGenerativeAI LLM instance using project settings."""
    api_key = settings.GEMINI_API_KEY or "mock-key"
    model_name = model or settings.GEMINI_MODEL
    temp = temperature if temperature is not None else settings.GEMINI_TEMPERATURE

    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=api_key,
        temperature=temp,
    )
