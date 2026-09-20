from documents.services.context_builder import build_context
from documents.services.embedder import generate_document_embedding
from documents.services.vector_search import search_similar_chunks

from ai.services.llm import generate_answer
from ai.services.source_builder import build_sources


class RAGGenerationError(Exception):
    """Raised when the RAG pipeline fails."""


def generate_rag_answer(
    question,
    organization_id,
    top_k=3,
):
    """
    Run the complete RAG pipeline:

    Question
        -> Embedding
        -> Vector Search
        -> Context Building
        -> LLM
        -> Sources
    """

    if not question or not question.strip():
        raise ValueError("Question cannot be empty.")

    try:
        # 1. Generate embedding for the user's question.
        query_embedding = generate_document_embedding(question)

        # 2. Retrieve the most relevant chunks.
        chunks = search_similar_chunks(
            query_embedding=query_embedding,
            organization_id=organization_id,
            top_k=top_k,
        )

        # 3. Build context for the LLM.
        context = build_context(chunks)

        if not context:
            return {
                "answer": (
                    "I couldn't find relevant information "
                    "in the provided documents."
                ),
                "sources": [],
            }

        # 4. Generate the answer using the retrieved context.
        answer = generate_answer(
            question=question,
            context=context,
        )

        # 5. Build source metadata for the API response.
        sources = build_sources(chunks)

        return {
            "answer": answer,
            "sources": sources,
        }

    except ValueError:
        raise

    except Exception as exc:
        raise RAGGenerationError(
            "Failed to generate RAG answer."
        ) from exc