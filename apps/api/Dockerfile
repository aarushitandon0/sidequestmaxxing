# Build context = repo root (so /prompts is available). See MASTERSPEC §12.4.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FASTEMBED_CACHE_PATH=/opt/fastembed

WORKDIR /srv

COPY apps/api/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

# Pre-download the embedding model at build time so cold starts don't hit Hugging Face.
COPY apps/api/scripts/preload_embeddings.py ./preload_embeddings.py
RUN python preload_embeddings.py && rm preload_embeddings.py

COPY apps/api/app ./app
COPY prompts /prompts
# Gate G1 benchmark, runnable from the Render shell: PYTHONPATH=/srv python scripts/bench_llm.py
COPY scripts/_bootstrap.py scripts/bench_llm.py ./scripts/

RUN useradd --create-home --uid 10001 app \
    && chown -R app:app /srv /opt/fastembed
USER app

ENV PROMPTS_DIR=/prompts
EXPOSE 10000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers"]
