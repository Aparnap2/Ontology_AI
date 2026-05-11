"""Memory Spine - orchestrates all 5 memory layers.

L1: Redis (working memory)
L2: Qdrant episodic
L3: Graphiti semantic + temporal
L4: PostgreSQL procedural
L5: Qdrant compressed (fallback only when L2 < 2 results)
"""
from dataclasses import dataclass, field
from typing import Optional

QDRANT_THRESHOLD = 0.82


@dataclass
class MemoryContext:
    working: Optional[dict] = None
    episodic: list[dict] = field(default_factory=list)
    semantic: list[dict] = field(default_factory=list)
    playbook: list[dict] = field(default_factory=list)
    procedural: list[dict] = field(default_factory=list)
    compressed: list[dict] = field(default_factory=list)
    total_layers_hit: int = 0
    errors: list[str] = field(default_factory=list)


async def load_context(
    tenant_id: str,
    query: str,
    domain: str
) -> MemoryContext:
    """Load context from all 5 memory layers in priority order."""
    ctx = MemoryContext()

    # L1 Redis working memory
    try:
        from src.memory.working import WorkingMemory
        wm = WorkingMemory(tenant_id=tenant_id, run_id="spine")
        ctx.working = wm.get("context")
    except Exception as e:
        ctx.errors.append(f"L1: {e}")

    # L2 Qdrant episodic
    try:
        from src.memory.episodic import EpisodicMemory
        em = EpisodicMemory(collection="episodes")
        results = em.search(
            tenant_id=tenant_id,
            query=query,
            top_k=5
        )
        ctx.episodic = [r for r in results if r.get("score", 0) >= QDRANT_THRESHOLD]
    except Exception as e:
        ctx.errors.append(f"L2: {e}")

    # L3 Graphiti semantic + temporal
    try:
        from src.memory.semantic import SemanticMemory
        sm = SemanticMemory(tenant_id=tenant_id)
        ctx.semantic = sm.search(query=query, num_results=5)
        ctx.playbook = []
    except Exception as e:
        ctx.errors.append(f"L3: {e}")

    # L4 Postgres procedural
    try:
        from src.memory.procedural import ProceduralMemory
        pm = ProceduralMemory()
        program = pm.load(tenant_id=tenant_id, agent=domain, signature="default")
        if program:
            ctx.procedural = [program]
    except Exception as e:
        ctx.errors.append(f"L4: {e}")

    # L5 Qdrant compressed - only if L2 sparse
    if len(ctx.episodic) < 2:
        try:
            from src.memory.compressed import CompressedMemory
            cm = CompressedMemory()
            ctx.compressed = cm.search(tenant_id=tenant_id, top_k=3)
        except Exception as e:
            ctx.errors.append(f"L5: {e}")

    ctx.total_layers_hit = sum([
        bool(ctx.working),
        bool(ctx.episodic),
        bool(ctx.semantic),
        bool(ctx.procedural),
        bool(ctx.compressed),
    ])

    return ctx