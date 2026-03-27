# Parallel Module Indexing — Final Implementation Guide

## TL;DR — What Can My System Handle?

With everything implemented (parallel modules + parallel embed/store + semaphores + parallel PDF extraction):

**Best case (Tier 1 limits):**

- **~25-30 users can index courses at the same time** without anyone hitting errors
- Each course (10-15 modules) finishes indexing in **~10-15 seconds** instead of ~90 seconds
- The system processes roughly **2,000 chunks per second** for embeddings
- If more than 30 users hit it at once, nobody fails — they just **wait in a queue**. A 50th user might wait 20-30 seconds longer, but their indexing still completes successfully

**The bottleneck is PDF processing (GPT-4o):**

- If courses have PDFs with images, GPT-4o vision is the slowest part (30K TPM limit)
- With `Semaphore(5)`, only 5 PDF pages process at a time across ALL users
- A course with lots of image-heavy PDFs takes ~15-20 seconds for the PDF step alone
- If courses have **no PDFs** (just text content), indexing is much faster (~5-8 seconds)

**Simple rule of thumb:**

- Text-only courses: **30+ concurrent users, no problem**
- PDF-heavy courses: **10-15 concurrent users comfortably**, more than that just queues up

After upgrading to **Tier 2** ($50 spent), GPT-4o TPM jumps to 450K and you can bump the PDF semaphore to 15 — roughly **3x more concurrent PDF processing**.

---

## Scaling Beyond Tier 1

When you upgrade to Tier 2+ ($50 cumulative spend), limits increase:

| Tier             | Embedding TPM | GPT-4o TPM | Action                                        |
| ---------------- | ------------- | ---------- | --------------------------------------------- |
| Tier 1 (current) | 1,000,000     | 30,000     | Semaphore(20) + Semaphore(5)                  |
| Tier 2           | 1,000,000     | 450,000    | Can increase to Semaphore(20) + Semaphore(15) |
| Tier 3           | 5,000,000     | 800,000    | Can increase to Semaphore(50) + Semaphore(30) |

Make semaphore values configurable via environment variables:

```python
# rate_limiters.py
import os, asyncio

EMBEDDING_SEMAPHORE = asyncio.Semaphore(
    int(os.getenv("MAX_CONCURRENT_EMBEDDINGS", "20"))
)
PDF_VISION_SEMAPHORE = asyncio.Semaphore(
    int(os.getenv("MAX_CONCURRENT_PDF_VISION", "5"))
)
```

Then in `docker-compose.yml` or `.env`, just update the values as you scale.
