# syntax=docker/dockerfile:1
#
# SDG Campus AI backend (FastAPI + RAG).
# Build context = repository root (the folder that contains api/ and requirements.txt).

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf_cache \
    HF_HUB_DISABLE_XET=1

WORKDIR /app

# 1) CPU-only PyTorch. The default build ships CUDA libraries (several GB);
#    the VM most likely has no GPU and the embedding model is small.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

# 2) Python dependencies. Separate layer: rebuilt only when requirements.txt changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

# 3) Non-root user and the directories the app writes to.
#    /app/data/chromadb is where api/rag/vector_store.py puts ChromaDB
#    (code lives in /app/api, so "../../data/chromadb" resolves to /app/data/chromadb).
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /opt/hf_cache /app/data/chromadb \
    && chown -R appuser:appuser /opt/hf_cache /app/data
USER appuser

# 4) Bake the embedding model into the image, so the container never has to
#    download anything from HuggingFace at start-up (the VM may have restricted
#    outbound access). If you change EMBEDDING_MODEL, rebuild the image.
ARG EMBEDDING_MODEL=paraphrase-multilingual-mpnet-base-v2
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"

# 5) Application code (last, because it changes most often).
COPY --chown=appuser:appuser api/ /app/api/
WORKDIR /app/api

EXPOSE 8001

# One worker on purpose: the embedding model and the ChromaDB PersistentClient
# live in the process memory and must not be duplicated across workers.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]