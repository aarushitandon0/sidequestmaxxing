"""Download the fastembed model into FASTEMBED_CACHE_PATH at image build time."""

import os

from fastembed import TextEmbedding

MODEL = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
TextEmbedding(model_name=MODEL, cache_dir=os.environ["FASTEMBED_CACHE_PATH"])
