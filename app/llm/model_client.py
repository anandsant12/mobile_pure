"""
Thin wrapper so planner.py, resolver.py, locator_engine.py, and verifier.py
all go through one place, and never know or care which provider is behind it.

ONE toggle in .env controls both text and vision:

  LLM_PROVIDER = "groq" | "azure"

  - groq  -> GROQ_MODEL is used for text/planning calls, GROQ_VISION_MODEL
             is used for vision calls.
  - azure -> AZURE_OPENAI_DEPLOYMENT is used for BOTH text and vision calls
             (point this at your gpt-4.1-mini deployment - it's multimodal,
             so one deployment covers both).

Provider notes:
  - Groq: uses the AsyncGroq client. Two quirks handled here that don't
    apply to Azure: reasoning models emit <think> blocks that must be
    hidden/stripped, and Groq's vision models are more reliable without a
    separate "system" role.
  - Azure OpenAI: uses AsyncAzureOpenAI. The "model" param must be your
    DEPLOYMENT NAME (set in Azure AI/OpenAI Studio), not the underlying
    model name like "gpt-4.1-mini".
"""

import json
import re

from openai import AsyncAzureOpenAI
from openai import BadRequestError as OpenAIBadRequestError
from groq import AsyncGroq
from groq import BadRequestError as GroqBadRequestError

from config import settings

MAX_TOKENS = 4096

_clients: dict = {}  # one cached client instance per provider name


def _token_kwarg_name(provider: str) -> str:
    # Groq's API (mirroring newer OpenAI reasoning-model conventions) wants
    # max_completion_tokens; Azure's chat-completions models want max_tokens.
    return "max_completion_tokens" if provider == "groq" else "max_tokens"


def _get_groq_client():
    if not settings.groq_api_key:
        raise RuntimeError(
            "Missing GROQ_API_KEY. Set LLM_PROVIDER=groq and fill this in your .env."
        )
    if "groq" not in _clients:
        _clients["groq"] = AsyncGroq(api_key=settings.groq_api_key)
    return _clients["groq"]


def _get_azure_client():
    missing = [
        name for name, val in [
            ("AZURE_OPENAI_API_KEY", settings.azure_openai_api_key),
            ("AZURE_OPENAI_ENDPOINT", settings.azure_openai_endpoint),
            ("AZURE_OPENAI_DEPLOYMENT", settings.azure_openai_deployment),
        ] if not val
    ]
    if missing:
        raise RuntimeError(
            f"Missing Azure OpenAI config: {', '.join(missing)}. "
            f"Set LLM_PROVIDER=azure and fill these in your .env."
        )
    if "azure" not in _clients:
        _clients["azure"] = AsyncAzureOpenAI(
            api_key=settings.azure_openai_api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
        )
    return _clients["azure"]


def _resolve_text_provider():
    provider = settings.llm_provider
    if provider == "groq":
        return provider, _get_groq_client(), settings.groq_model
    if provider == "azure":
        return provider, _get_azure_client(), settings.azure_openai_deployment
    raise RuntimeError(f"Unknown LLM_PROVIDER '{provider}'. Use 'groq' or 'azure'.")


def _resolve_vision_provider():
    provider = settings.llm_provider
    if provider == "groq":
        return provider, _get_groq_client(), settings.groq_vision_model
    if provider == "azure":
        # Same deployment as text - gpt-4.1-mini handles both.
        return provider, _get_azure_client(), settings.azure_openai_deployment
    raise RuntimeError(f"Unknown LLM_PROVIDER '{provider}'. Use 'groq' or 'azure'.")


def _strip_think_blocks(raw: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL).strip()
    if "<think>" in cleaned:
        cleaned = cleaned.split("<think>")[0].strip()
    return cleaned


def _extract_json(raw: str) -> dict:
    if not raw or not raw.strip():
        raise ValueError("Empty response from model")

    cleaned = _strip_think_blocks(raw)
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    if not cleaned:
        raise ValueError("Empty response from model after stripping reasoning")

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        return json.loads(match.group(0))

    raise ValueError(f"Could not parse JSON from model output: {raw!r}")


async def _complete(provider: str, client, model: str, messages: list,
                     force_json: bool = True, hide_reasoning: bool = True) -> str:
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        _token_kwarg_name(provider): MAX_TOKENS,
    }
    if force_json:
        kwargs["response_format"] = {"type": "json_object"}
    if provider == "groq" and hide_reasoning:
        kwargs["reasoning_format"] = "hidden"

    try:
        completion = await client.chat.completions.create(**kwargs)
        return completion.choices[0].message.content
    except (GroqBadRequestError, OpenAIBadRequestError):
        if provider == "groq" and hide_reasoning:
            return await _complete(provider, client, model, messages, force_json=force_json, hide_reasoning=False)
        if force_json:
            return await _complete(provider, client, model, messages, force_json=False, hide_reasoning=False)
        raise


async def _call_and_parse(provider: str, client, model: str, messages: list) -> dict:
    raw = await _complete(provider, client, model, messages, force_json=True)
    try:
        return _extract_json(raw)
    except ValueError:
        retry_messages = messages + [
            {"role": "assistant", "content": raw or ""},
            {"role": "user", "content": "That was not valid JSON. Reply again with ONLY a single "
                                         "valid JSON object, no <think> tags, no markdown fences, no other text."},
        ]
        raw2 = await _complete(provider, client, model, retry_messages, force_json=False)
        return _extract_json(raw2)


async def achat_json(system_prompt: str, user_prompt: str) -> dict:
    """Text-only planning/reasoning call. Provider chosen via LLM_PROVIDER."""
    provider, client, model = _resolve_text_provider()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return await _call_and_parse(provider, client, model, messages)


async def achat_vision_json(system_prompt: str, user_prompt: str, image_b64: str) -> dict:
    """Vision call (screenshot -> JSON). Provider chosen via LLM_PROVIDER."""
    provider, client, model = _resolve_vision_provider()

    if provider == "groq":
        # Groq's vision models are more reliable with everything folded into
        # one user text block alongside the image, no separate system role.
        combined_text = f"{system_prompt.strip()}\n\n{user_prompt.strip()}"
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": combined_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                ],
            },
        ]
    else:
        # Azure OpenAI (gpt-4.1-mini) works fine with a normal
        # system + user(text+image) shape.
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                ],
            },
        ]

    return await _call_and_parse(provider, client, model, messages)
