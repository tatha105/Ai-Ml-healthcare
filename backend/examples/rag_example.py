"""Small RAG example. No API key required.

RAG = Retrieval-Augmented Generation.

1. Store documents (policy clauses).
2. Turn each document into a vector (embed).
3. Turn the question into a vector and keep the closest documents (retrieve).
4. Answer using only those documents (generate).

A production system swaps the hash embedder for Azure OpenAI embeddings
and swaps answer() for a LangChain call to GPT-5.1. The four steps stay the same.
"""

from __future__ import annotations

import math
import re

# One clause is one document. In a bigger system you would split long PDFs into chunks.
DOCUMENTS = [
    {
        "id": "CL-ROOM",
        "text": "Silver plan: room rent is payable up to Rs 3,000 per day. Rent above the cap is the member's share.",
    },
    {
        "id": "CL-WAIT",
        "text": "On a new Gold policy, arthroscopy is covered only after 90 days from the policy start.",
    },
    {
        "id": "CL-NET",
        "text": "Cashless admission is limited to network hospitals. A non-network hospital is not payable under cashless.",
    },
    {
        "id": "CL-SURG",
        "text": "Medically necessary inpatient treatment is payable up to the remaining sum insured.",
    },
]


def tokens(text: str) -> list[str]:
    """Lowercase words. Punctuation is dropped so 'hospitals.' and 'hospitals' match."""
    return re.findall(r"[a-z0-9]+", text.lower())


def embed(text: str) -> dict[str, float]:
    """Turn text into a vector of word counts.

    Each word is one dimension. 'room rent cap' and 'room rent limit' sit near
    each other because they share words. Azure OpenAI embeddings do the same
    job with a denser vector that also understands synonyms.
    """
    vector: dict[str, float] = {}
    for word in tokens(text):
        vector[word] = vector.get(word, 0.0) + 1.0
    return vector


def cosine(left: dict[str, float], right: dict[str, float]) -> float:
    """1.0 means the same direction. 0.0 means no shared words."""
    if not left or not right:
        return 0.0
    shared = set(left) & set(right)
    dot = sum(left[word] * right[word] for word in shared)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def index_documents(documents: list[dict]) -> list[dict]:
    """Embed every document once. This is the index you would store in a vector database."""
    indexed = []
    for document in documents:
        indexed.append({**document, "vector": embed(document["text"])})
    return indexed


def retrieve(question: str, index: list[dict], k: int = 2) -> list[dict]:
    """Return the k documents closest to the question."""
    question_vector = embed(question)
    scored = []
    for document in index:
        scored.append({**document, "score": cosine(question_vector, document["vector"])})
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:k]


def answer(question: str, hits: list[dict]) -> str:
    """Answer from the retrieved text only.

    The prompt below is what you would send to GPT-5.1 through LangChain.
    Without a model, this function quotes the best clause so the answer
    cannot invent a benefit that was not retrieved.
    """
    context = "\n".join(f"{hit['id']}: {hit['text']}" for hit in hits)
    prompt = (
        "Answer the question using only the clauses below. "
        "If they do not contain the answer, say you do not know.\n\n"
        f"Clauses:\n{context}\n\nQuestion: {question}"
    )
    best = hits[0]
    if best["score"] <= 0:
        return "I do not know. No clause matched the question.\n\nPrompt that would go to the model:\n" + prompt
    return (
        f"{best['text']} (clause {best['id']})\n\n"
        f"Prompt that would go to the model:\n{prompt}"
    )


def ask(question: str, index: list[dict]) -> None:
    hits = retrieve(question, index, k=2)
    print(f"Q: {question}")
    print("Retrieved:")
    for hit in hits:
        print(f"  {hit['score']:.2f}  {hit['id']}  {hit['text']}")
    print("A:", answer(question, hits))
    print()


def main() -> None:
    index = index_documents(DOCUMENTS)
    ask("What is the room rent cap on the Silver plan?", index)
    ask("When is arthroscopy covered on a new policy?", index)
    ask("Is a non-network hospital payable as cashless?", index)


if __name__ == "__main__":
    main()
