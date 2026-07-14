#!/usr/bin/env python3
"""
Setup Qdrant collections for OntologyAI v1.0.

Creates:
- finance_memory: Finance Agent episodic memory (768-dim)
- bi_memory: BI Agent query memory (768-dim)

Uses nomic-embed-text:latest via Ollama (768 dimensions).
"""
import os
import requests
from typing import List

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text:latest")
VECTOR_SIZE = 768  # nomic-embed-text output dimension


def check_ollama() -> bool:
    """Verify Ollama is running and has embedding model."""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        models = resp.json().get("models", [])
        model_names = [m.get("name", "") for m in models]
        
        if EMBEDDING_MODEL not in model_names:
            print(f"❌ Embedding model '{EMBEDDING_MODEL}' not found in Ollama")
            print(f"   Available models: {', '.join(model_names)}")
            return False
        
        print(f"✅ Ollama running with {EMBEDDING_MODEL}")
        return True
    except Exception as e:
        print(f"❌ Ollama not reachable: {e}")
        return False


def check_qdrant() -> bool:
    """Verify Qdrant is running."""
    try:
        resp = requests.get(f"{QDRANT_URL}/healthz", timeout=5)
        resp.raise_for_status()
        print(f"✅ Qdrant healthy at {QDRANT_URL}")
        return True
    except Exception as e:
        print(f"❌ Qdrant not reachable: {e}")
        return False


def get_embedding(text: str) -> List[float]:
    """Get embedding from Ollama with backward compatibility."""
    # Try new /api/embed endpoint first
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/embed",
            json={
                "model": EMBEDDING_MODEL,
                "input": text,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        # New endpoint returns "embeddings" key
        embeddings = data.get("embeddings")
        if embeddings and isinstance(embeddings, list) and len(embeddings) > 0:
            return embeddings[0] if isinstance(embeddings[0], list) else embeddings
    except Exception:
        pass  # Fall back to old endpoint
    
    # Fallback to deprecated /api/embeddings endpoint
    resp = requests.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={
            "model": EMBEDDING_MODEL,
            "prompt": text,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("embedding", [])


def create_collection(name: str) -> bool:
    """Create Qdrant collection if it doesn't exist, with schema validation."""
    try:
        # Check if collection exists
        resp = requests.get(f"{QDRANT_URL}/collections/{name}", timeout=5)

        if resp.status_code == 200:
            # Validate schema on existing collection
            try:
                data = resp.json()
                config = data.get("result", {}).get("config", {})
                params = config.get("params", {})
                vectors_config = params.get("vectors", {})
                
                # Handle both simple and complex vector configs
                if isinstance(vectors_config, dict):
                    actual_size = vectors_config.get("size")
                    actual_distance = vectors_config.get("distance")
                else:
                    actual_size = VECTOR_SIZE  # Default assumption
                    actual_distance = "Cosine"
                
                if actual_size != VECTOR_SIZE:
                    print(f"❌ Collection '{name}' exists but has wrong vector size: "
                          f"got {actual_size}, expected {VECTOR_SIZE}")
                    return False
                if actual_distance != "Cosine":
                    print(f"❌ Collection '{name}' exists but has wrong distance: "
                          f"got {actual_distance}, expected Cosine")
                    return False
                    
                print(f"✅ Collection '{name}' already exists (validated: {VECTOR_SIZE}-dim, Cosine)")
                return True
            except (KeyError, TypeError) as e:
                print(f"⚠️  Collection '{name}' exists but schema validation skipped: {e}")
                return True

        # Create collection
        resp = requests.put(
            f"{QDRANT_URL}/collections/{name}",
            json={
                "vectors": {
                    "size": VECTOR_SIZE,
                    "distance": "Cosine",
                },
                "optimizers_config": {
                    "default_segment_number": 2,
                },
                "on_disk_payload": True,
            },
            timeout=10,
        )
        resp.raise_for_status()

        result = resp.json()
        # Qdrant returns {"result": true, "status": "ok", "time": ...}
        result_value = result.get("result")
        if result_value is True or (isinstance(result_value, dict) and result_value.get("acknowledged", False)):
            print(f"✅ Collection '{name}' created ({VECTOR_SIZE}-dim, Cosine)")
            return True
        else:
            print(f"❌ Failed to create collection '{name}'")
            return False

    except Exception as e:
        print(f"❌ Error creating collection '{name}': {e}")
        return False


def test_collection(name: str) -> bool:
    """Test collection by inserting and querying a sample point."""
    try:
        # Get test embedding
        test_text = f"Test {name} embedding"
        vector = get_embedding(test_text)
        
        if not vector or len(vector) != VECTOR_SIZE:
            print(f"❌ Embedding dimension mismatch: got {len(vector)}, expected {VECTOR_SIZE}")
            return False
        
        # Upsert test point
        resp = requests.put(
            f"{QDRANT_URL}/collections/{name}/points",
            json={
                "points": [
                    {
                        "id": 999,
                        "vector": vector,
                        "payload": {
                            "test": True,
                            "text": test_text,
                        },
                    }
                ],
            },
            timeout=10,
        )
        resp.raise_for_status()
        
        # Query test point
        resp = requests.post(
            f"{QDRANT_URL}/collections/{name}/points/search",
            json={
                "vector": vector,
                "limit": 1,
                "with_payload": True,
            },
            timeout=10,
        )
        resp.raise_for_status()
        
        results = resp.json().get("result", [])
        if not results:
            print(f"❌ No results from test query on '{name}'")
            return False
        
        # Clean up test point
        requests.delete(
            f"{QDRANT_URL}/collections/{name}/points",
            json={"points": [999]},
            timeout=5,
        )
        
        print(f"✅ Collection '{name}' tested successfully")
        return True
        
    except Exception as e:
        print(f"❌ Error testing collection '{name}': {e}")
        return False


def main():
    """Main setup function."""
    print("╔══════════════════════════════════════════════════════════╗")
    print("║     SARTHI v1.0 — QDRANT COLLECTIONS SETUP              ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()
    
    # Check prerequisites
    print("1. Checking prerequisites...")
    if not check_ollama():
        print("\n❌ Aborting: Ollama not ready")
        return False
    
    if not check_qdrant():
        print("\n❌ Aborting: Qdrant not ready")
        return False
    
    print()
    
    # Create collections
    print("2. Creating collections...")
    collections = ["finance_memory", "bi_memory"]
    
    success = True
    for collection in collections:
        if not create_collection(collection):
            success = False
    
    if not success:
        print("\n❌ Some collections failed to create")
        return False
    
    print()
    
    # Test collections
    print("3. Testing collections...")
    for collection in collections:
        if not test_collection(collection):
            success = False
    
    print()
    
    if success:
        print("╔══════════════════════════════════════════════════════════╗")
        print("║     ✅ QDRANT COLLECTIONS READY                         ║")
        print("╚══════════════════════════════════════════════════════════╝")
        print()
        print(f"Collections created:")
        print(f"  - finance_memory ({VECTOR_SIZE}-dim, Cosine)")
        print(f"  - bi_memory ({VECTOR_SIZE}-dim, Cosine)")
        print()
        print("✅ PHASE 1B COMPLETE")
        print("✅ READY FOR PHASE 1C (REDPANDA TOPICS)")
        return True
    else:
        print("\n❌ Some collections failed testing")
        return False


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
