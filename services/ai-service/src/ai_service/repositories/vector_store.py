"""Vector store repository for Qdrant operations."""

import uuid
import uuid as _uuid
import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from ai_service.config import settings

logger = structlog.get_logger(__name__)

# Embedding dimension for text-embedding-3-small
EMBEDDING_DIMENSION = 1536


class VectorStoreRepository:
    """Qdrant vector store operations for RAG."""

    def __init__(self):
        self.client: AsyncQdrantClient | None = None
        self.collection_name = settings.QDRANT_COLLECTION

    async def connect(self) -> None:
        """Initialize async Qdrant client and ensure collection exists."""
        self.client = AsyncQdrantClient(url=settings.QDRANT_URL, check_compatibility=False)

        # Create collection if it doesn't exist
        collections = await self.client.get_collections()
        existing_names = [c.name for c in collections.collections]

        if self.collection_name not in existing_names:
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIMENSION,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(
                "Created Qdrant collection",
                collection=self.collection_name,
                dimension=EMBEDDING_DIMENSION,
            )

            # Create payload indexes for fast filtering
            for field in ["course_id", "module_id", "lesson_id"]:
                await self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field,
                    field_schema="keyword",
                )

            logger.info("Created payload indexes for filtering")
        else:
            logger.info("Qdrant collection already exists", collection=self.collection_name)

    async def close(self) -> None:
        """Close the Qdrant client."""
        if self.client:
            await self.client.close()
            self.client = None

    async def upsert_chunks(
        self,
        course_id: _uuid.UUID,
        module_id: str,
        lesson_id: str,
        chunks: list[dict],
    ) -> int:
        """Store embedding chunks with metadata.

        Args:
            course_id: Course ID
            module_id: Module ID (ObjectId hex string)
            lesson_id: Lesson ID (ObjectId hex string)
            chunks: List of dicts, each with:
                - text: str (the chunk text)
                - embedding: list[float] (the embedding vector)
                - chunk_index: int
                - lesson_title: str
                - module_title: str

        Returns:
            Number of points stored.
        """
        if not chunks:
            return 0

        points = []
        for chunk in chunks:
            point_id = str(uuid.uuid4())
            points.append(
                PointStruct(
                    id=point_id,
                    vector=chunk["embedding"],
                    payload={
                        "text": chunk["text"],
                        "course_id": str(course_id),
                        "module_id": module_id,
                        "lesson_id": lesson_id,
                        "chunk_index": chunk["chunk_index"],
                        "lesson_title": chunk.get("lesson_title", ""),
                        "module_title": chunk.get("module_title", ""),
                        "preview": chunk["text"][:200],
                    },
                )
            )

        # Upsert in batches of 100 (Qdrant handles large batches well,
        # but batching avoids memory spikes for huge courses)
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            await self.client.upsert(
                collection_name=self.collection_name,
                points=batch,
            )

        logger.info(
            "Upserted chunks to Qdrant",
            course_id=course_id,
            module_id=module_id,
            lesson_id=lesson_id,
            num_chunks=len(points),
        )
        return len(points)

    async def search(
        self,
        query_embedding: list[float],
        course_id: _uuid.UUID,
        module_id: str | None = None,
        lesson_id: str | None = None,
        top_k: int = 5,
    ) -> list[dict]:
        """Search for relevant chunks by vector similarity.

        Args:
            query_embedding: The query embedding vector.
            course_id: Filter to this course.
            module_id: Optionally filter to a specific module.
            lesson_id: Optionally filter to a specific lesson.
            top_k: Number of results to return.

        Returns:
            List of dicts with: text, score, course_id, module_id, lesson_id,
            chunk_index, lesson_title, module_title.
        """
        # Build filter conditions
        must_conditions = [FieldCondition(key="course_id", match=MatchValue(value=str(course_id)))]
        if module_id:
            must_conditions.append(
                FieldCondition(key="module_id", match=MatchValue(value=module_id))
            )
        if lesson_id:
            must_conditions.append(
                FieldCondition(key="lesson_id", match=MatchValue(value=lesson_id))
            )

        results = await self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            query_filter=Filter(must=must_conditions),
            limit=top_k,
            with_payload=True,
        )

        return [
            {
                "text": point.payload.get("text", ""),
                "score": point.score,
                "course_id": point.payload.get("course_id"),
                "module_id": point.payload.get("module_id"),
                "lesson_id": point.payload.get("lesson_id"),
                "chunk_index": point.payload.get("chunk_index"),
                "lesson_title": point.payload.get("lesson_title"),
                "module_title": point.payload.get("module_title"),
            }
            for point in results.points
        ]

    async def delete_course_vectors(self, course_id: _uuid.UUID) -> None:
        """Delete all vectors for a course."""
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="course_id",
                        match=MatchValue(value=str(course_id)),
                    )
                ]
            ),
        )
        logger.info("Deleted course vectors from Qdrant", course_id=course_id)

    async def delete_module_vectors(self, course_id: _uuid.UUID, module_id: str) -> None:
        """Delete all vectors for a module."""
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="course_id",
                        match=MatchValue(value=str(course_id)),
                    ),
                    FieldCondition(
                        key="module_id",
                        match=MatchValue(value=module_id),
                    ),
                ]
            ),
        )
        logger.info(
            "Deleted module vectors from Qdrant",
            course_id=course_id,
            module_id=module_id,
        )

    async def get_collection_info(self) -> dict:
        """Get collection stats (useful for status endpoint)."""
        info = await self.client.get_collection(self.collection_name)
        return {
            "total_points": info.points_count,
            "vectors_count": info.vectors_count,
            "status": info.status.value,
        }

    async def count_course_vectors(self, course_id: _uuid.UUID) -> int:
        """Count vectors for a specific course."""
        result = await self.client.count(
            collection_name=self.collection_name,
            count_filter=Filter(
                must=[
                    FieldCondition(
                        key="course_id",
                        match=MatchValue(value=str(course_id)),
                    )
                ]
            ),
        )
        return result.count
