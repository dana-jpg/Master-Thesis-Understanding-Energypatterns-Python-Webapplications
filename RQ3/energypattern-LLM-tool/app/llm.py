import os
from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

# Model tiers for cost optimization
MODEL_TIERS = {
    "fast": "llama-3.1-8b-instant",      
    "deep": "llama-3.3-70b-versatile",   
}


def get_llm(
    provider: str = "groq",
    model: str = None,
    tier: str = "deep",
) -> BaseChatModel:
    """
    Get an LLM instance.
    
    Args:
        provider: LLM provider ("groq", "ollama", "gemini")
        model: Explicit model name (overrides tier)
        tier: Model tier - "fast" for pre-filtering, "deep" for analysis
    """
    # Use explicit model if provided, otherwise use tier
    if model is None:
        model = MODEL_TIERS.get(tier, MODEL_TIERS["deep"])
    if provider == "ollama":
        return ChatOllama(
            model=model,
            temperature=0,
        )
    
    elif provider == "gemini":
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY environment variable is required for Gemini provider. "
                "Get your API key at https://ai.google.dev/"
            )
        
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key,
            temperature=0,
        )

    elif provider == "groq":
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY environment variable is required for Groq provider. "
                "Get your API key at https://console.groq.com/keys"
            )
        
        return ChatGroq(
            model_name=model,
            groq_api_key=api_key,
            temperature=0,
        )

    raise ValueError(f"Unknown LLM provider: {provider}")


