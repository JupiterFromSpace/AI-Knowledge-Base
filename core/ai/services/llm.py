import logging

from django.conf import settings
from google import genai


logger = logging.getLogger(__name__)

LLM_MODEL = "gemini-3.6-flash"


class LLMGenerationError(Exception):
    """Raised when LLM answer generation fails."""


_client = None


def get_client():
    """Return a cached Gemini client."""

    global _client

    if _client is None:
        api_key = getattr(settings, "GEMINI_API_KEY", None)

        if not api_key:
            raise LLMGenerationError(
                "GEMINI_API_KEY is not configured."
            )

        _client = genai.Client(api_key=api_key)

    return _client


def generate_answer(question, context):
    """
    Generate an answer using the provided question and retrieved context.
    """

    if not question or not question.strip():
        raise ValueError("Question cannot be empty.")

    if not context or not context.strip():
        raise ValueError("Context cannot be empty.")

    system_instruction = """
You are an AI assistant answering questions based only on the provided context.

Rules:
- Answer the user's question using only the provided context.
- Do not use outside knowledge.
- If the answer cannot be found in the context, clearly say that the information is not available in the provided documents.
- Do not invent or assume information.
- Keep the answer concise and directly relevant.
- When possible, mention the source number that supports your answer.
"""

    prompt = f"""
Context:

{context}

Question:

{question}
"""

    try:
        client = get_client()

        interaction = client.interactions.create(
            model=LLM_MODEL,
            input=prompt,
            system_instruction=system_instruction,
        )

        answer = interaction.output_text

        if not answer:
            raise LLMGenerationError(
                "LLM returned an empty response."
            )

        return answer.strip()

    except LLMGenerationError:
        raise

    except Exception as exc:
        logger.exception("LLM answer generation failed.")

        raise LLMGenerationError(
            "Failed to generate answer from LLM."
        ) from exc