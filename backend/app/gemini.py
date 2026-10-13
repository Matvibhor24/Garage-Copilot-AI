"""One place for non-live Gemini calls (vision captions, translation, embeddings). Tests stub `generate` and `embed`.
Credentials come from the environment: Vertex AI (GOOGLE_GENAI_USE_VERTEXAI, GOOGLE_CLOUD_PROJECT,
GOOGLE_CLOUD_LOCATION) or GOOGLE_API_KEY."""

from google.genai import types

_client = None


def _get_client():
    global _client
    if _client is None:
        from google import genai

        _client = genai.Client()
    return _client


def generate(model: str, prompt: str, image: bytes | None = None, mime_type: str = "image/jpeg") -> str:
    contents = [prompt]
    if image is not None:
        contents.insert(0, types.Part.from_bytes(data=image, mime_type=mime_type))
    response = _get_client().models.generate_content(model=model, contents=contents)
    return (response.text or "").strip()


def embed(texts: list[str], task_type: str) -> list[list[float]]:
    """Embeddings for manual chunks (task_type RETRIEVAL_DOCUMENT) or questions (RETRIEVAL_QUERY),
    EMBED_DIM long, EMBED_BATCH texts per call."""
    from app import config

    out = []
    for i in range(0, len(texts), max(1, config.EMBED_BATCH)):
        batch = texts[i:i + max(1, config.EMBED_BATCH)]
        response = _get_client().models.embed_content(
            model=config.EMBED_MODEL, contents=batch,
            config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=config.EMBED_DIM))
        out += [list(e.values) for e in response.embeddings]
    return out


LANGUAGES = {"en": "English", "hi": "Hindi", "mr": "Marathi", "gu": "Gujarati", "kn": "Kannada",
             "ta": "Tamil", "te": "Telugu", "bn": "Bengali", "ml": "Malayalam", "pa": "Punjabi"}


def translate(text: str, lang: str) -> str:
    """Customer message in their language. Keeps links, numbers, ₹ amounts and part names intact.
    Falls back to the original text if Gemini fails: a message in English beats no message."""
    if not lang or lang == "en" or lang not in LANGUAGES:
        return text
    from app import config

    prompt = (f"Translate this WhatsApp message from a vehicle garage to its customer into {LANGUAGES[lang]}. "
              "Keep every URL, number, ₹ amount, job/quote id and person name exactly as written. "
              "Use simple everyday words. Reply with the translation only.\n\n" + text)
    try:
        return generate(config.TEXT_MODEL, prompt) or text
    except Exception:
        import logging

        logging.getLogger(__name__).exception("translation to %s failed; sending English", lang)
        return text
