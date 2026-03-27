"""Global rate-limiting semaphores for external API calls.

These are module-level singletons shared across all concurrent tasks
in the asyncio event loop. They prevent overwhelming external services
(OpenAI, etc.) when multiple users trigger indexing simultaneously.

Semaphore value = max concurrent calls system-wide (not per-user).
"""

import os
import asyncio

# text-embedding-3-small: 1M TPM, 3000 RPM
# Each batch ≈ 37,500 tokens → safe max ≈ 26 concurrent batches
# We use 20 to leave headroom for search-time embed_query calls
EMBEDDING_SEMAPHORE = asyncio.Semaphore(int(os.getenv("MAX_CONCURRENT_EMBEDDINGS", "20")))

# gpt-4o (PDF image descriptions): 30K TPM, 500 RPM
# Each call ≈ 1,500 tokens → safe max ≈ 20 concurrent calls
# We use 5 because PDF processing is bursty (many pages per PDF)
PDF_VISION_SEMAPHORE = asyncio.Semaphore(int(os.getenv("MAX_CONCURRENT_PDF_VISION", "5")))

# whisper-1: 500 RPM, 25 MB per request
# We use 10 concurrent calls — safe for bursty transcription workloads
AUDIO_TRANSCRIPTION_SEMAPHORE = asyncio.Semaphore(
    int(os.getenv("MAX_CONCURRENT_AUDIO_TRANSCRIPTION", "10"))
)
