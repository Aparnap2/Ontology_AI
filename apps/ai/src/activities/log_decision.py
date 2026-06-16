"""
Log Decision Activity for Temporal.

Inserts decision to Postgres and Qdrant for retrieval.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

import psycopg2
from psycopg2.extras import RealDictCursor
from qdrant_client.models import PointStruct
from temporalio import activity

from src.config.database import get_database_url
from src.memory.qdrant_ops import _get_embedding
from src.services.embeddings import get_embeddings_service

log = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = get_database_url()

# Qdrant decisions collection
DECISIONS_COLLECTION = "decisions"


def _get_db_connection():
    """Get database connection."""
    return psycopg2.connect(DATABASE_URL)


def _ensure_decisions_collection():
    """Ensure decisions collection exists in Qdrant."""
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams

    client = QdrantClient(host="localhost", port=6333)
    try:
        client.get_collection(DECISIONS_COLLECTION)
    except Exception:
        client.create_collection(
            collection_name=DECISIONS_COLLECTION,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )


@activity.defn(name="log_decision")
async def log_decision(decision_data: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    """
    Log a decision to Postgres and Qdrant.

    Args:
        decision_data: Dict with 'decided', 'alternatives', 'reasoning'
        tenant_id: Tenant identifier

    Returns:
        dict with 'ok' and optional 'error'
    """
    if not tenant_id or not tenant_id.strip():
        return {"ok": False, "error": "tenant_id is required"}

    if not decision_data.get("decided"):
        return {"ok": False, "error": "decision is required"}

    try:
        # Insert to Postgres
        conn = _get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO decisions (tenant_id, decided, alternatives, reasoning)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (
            tenant_id,
            decision_data["decided"],
            decision_data.get("alternatives"),
            decision_data.get("reasoning")
        ))

        decision_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        # Generate embedding for Qdrant
        embedding_text = f"{decision_data['decided']} {decision_data.get('reasoning', '')}"
        embeddings_service = await get_embeddings_service()
        embedding_result = await embeddings_service.embed(embedding_text)

        # Upsert to Qdrant decisions collection
        from qdrant_client import QdrantClient

        _ensure_decisions_collection()
        client = QdrantClient(host="localhost", port=6333)

        point_id = str(uuid4())

        payload = {
            "tenant_id": tenant_id,
            "decision_id": decision_id,
            "decided": decision_data["decided"],
            "alternatives": decision_data.get("alternatives"),
            "reasoning": decision_data.get("reasoning"),
            "created_at": datetime.utcnow().timestamp(),
        }

        client.upsert(
            collection_name=DECISIONS_COLLECTION,
            points=[
                PointStruct(
                    id=point_id,
                    vector=embedding_result.embedding,
                    payload=payload,
                )
            ],
        )

        return {"ok": True, "decision_id": decision_id}

    except Exception as e:
        log.error(f"Failed to log decision for tenant {tenant_id}: {e}")
        return {"ok": False, "error": str(e)}