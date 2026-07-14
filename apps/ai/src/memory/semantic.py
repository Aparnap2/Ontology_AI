"""Layer 3: Semantic Memory — Graphiti + Neo4j graph DB.

All configuration via environment variables:
- OPENROUTER_API_KEY: For LLM + embeddings via OpenRouter
- OPENROUTER_BASE_URL: Defaults to https://openrouter.ai/api/v1
- NEO4J_URI: Defaults to bolt://localhost:7687
- GOOGLE_API_KEY: Fallback LLM when OpenRouter rate-limited (429)
"""
from __future__ import annotations
import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Load .env at module import time so all env vars are available early
_env_loaded = False
if not _env_loaded and not os.environ.get("OPENROUTER_API_KEY"):
    try:
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k not in os.environ:
                        os.environ[k] = v
    except Exception:
        pass
_env_loaded = True

try:
    from graphiti_core import Graphiti
    from graphiti_core.nodes import EpisodeType
    GRAPHITI_AVAILABLE = True
except ImportError:
    GRAPHITI_AVAILABLE = False
    Graphiti = None
    EpisodeType = None


def _get_neo4j_config() -> tuple[str, str, str]:
    """Get Neo4j connection config from environment."""
    return (
        os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        os.environ.get("NEO4J_USER", "neo4j"),
        os.environ.get("NEO4J_PASSWORD", "neo4j_password"),
    )





def _create_google_llm_client(api_key: str) -> Any:
    """Create a Google Gemini LLM client for Graphiti.
    
    Creates a proper subclass that inherits from LLMClient to pass
    Graphiti's isinstance check.
    """
    from graphiti_core.llm_client import LLMClient
    from google import genai
    
    class GoogleLLMClientImpl(LLMClient):
        """Google Gemini LLM client for Graphiti."""
        
        def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
            from graphiti_core.llm_client import LLMConfig
            config = LLMConfig(api_key=api_key, model=model)
            super().__init__(config=config)
            self._client = genai.Client(api_key=api_key)
            self._model = model
        
        async def generate_response(
            self,
            messages: list[Any],
            response_model: type | None = None,
            max_tokens: int | None = None,
            model_size: str = "medium",
            group_id: str | None = None,
            prompt_name: str | None = None,
        ) -> dict[str, Any]:
            """Generate a response using Google's Gemini (async)."""
            import json
            
            # Convert messages to Gemini format
            # Handle both dict messages and Pydantic Message objects
            chat_contents = []
            for msg in messages:
                # Handle dict messages (older format) or Message objects (Pydantic)
                if hasattr(msg, 'model_dump'):
                    # It's a Pydantic model (Message object)
                    msg_dict = msg.model_dump()
                elif hasattr(msg, 'dict'):
                    # It's a Pydantic model (older version)
                    msg_dict = msg.dict()
                else:
                    # It's already a dict
                    msg_dict = msg
                
                role = msg_dict.get("role", "user")
                content = msg_dict.get("content", "")
                gemini_role = "model" if role == "assistant" else "user"
                chat_contents.append({"role": gemini_role, "parts": [{"text": content}]})
            
            # If we have a response_model, inject JSON instruction
            if response_model:
                schema = response_model.model_json_schema()
                json_instruction = f"\n\nRespond ONLY with valid JSON matching this schema:\n{json.dumps(schema)}"
                if chat_contents and chat_contents[-1]["role"] == "user":
                    chat_contents[-1]["parts"][0]["text"] += json_instruction
            
            # Configure generation params
            generation_config = {
                "temperature": 0.1,
                "max_output_tokens": max_tokens or 4096,
            }
            
            # Map model_size to actual models
            model_map = {
                "small": "gemini-1.5-flash-8b",
                "medium": "gemini-2.0-flash",
                "large": "gemini-2.0-flash",
            }
            actual_model = model_map.get(model_size, "gemini-2.0-flash")
            
            try:
                response = self._client.models.generate_content(
                    model=actual_model,
                    contents=chat_contents,
                    config=generation_config,
                )
                
                text = response.text
                
                if response_model:
                    try:
                        parsed = json.loads(text)
                        if isinstance(parsed, dict):
                            return parsed
                        return {"response": parsed}
                    except json.JSONDecodeError:
                        import re
                        json_match = re.search(r"\{.*\}", text, re.DOTALL)
                        if json_match:
                            return json.loads(json_match.group())
                
                return {"response": text}
            except Exception as e:
                return {"error": str(e)}
        
        def set_tracer(self, tracer: Any) -> None:
            """Set a tracer for logging/debugging (optional)."""
            pass
        
        def _generate_response(
            self,
            messages: list[Any],
            response_model: type | None = None,
            max_tokens: int | None = None,
            model_size: str = "medium",
            group_id: str | None = None,
            prompt_name: str | None = None,
        ) -> dict[str, Any]:
            """Internal method for generating response.
            
            This is an alias for generate_response to satisfy the abstract base class.
            """
            return self.generate_response(
                messages=messages,
                response_model=response_model,
                max_tokens=max_tokens,
                model_size=model_size,
                group_id=group_id,
                prompt_name=prompt_name,
            )
    
    return GoogleLLMClientImpl(api_key=api_key)

    def generate_response(
        self,
        messages: list[Any],
        response_model: type | None = None,
        max_tokens: int | None = None,
        model_size: str = "medium",
        group_id: str | None = None,
        prompt_name: str | None = None,
    ) -> dict[str, Any]:
        """Generate a response using Google's Gemini.

        Args:
            messages: List of message dicts with 'role' and 'content'
            response_model: Pydantic model to parse response into (optional)
            max_tokens: Max tokens to generate
            model_size: 'small', 'medium', or 'large' - maps to Gemini models
            group_id: Group ID for context (optional)
            prompt_name: Name of prompt template (optional)

        Returns:
            Dict with response content that Graphiti can parse
        """
        import json

        # Convert messages to Gemini format
        # Build system prompt from first message if it's a system message
        system_instruction = ""
        chat_contents = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_instruction = content
            else:
                # Gemini uses 'model' for assistant, 'user' for user
                gemini_role = "model" if role == "assistant" else "user"
                chat_contents.append({"role": gemini_role, "parts": [{"text": content}]})

        # Use the latest user message as the prompt
        user_prompt = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_prompt = msg.get("content", "")
                break

        # If we have a response_model, inject JSON instruction
        if response_model:
            # Get the expected schema from the pydantic model
            schema = response_model.model_json_schema()
            # Add JSON instruction to the user prompt
            json_instruction = f"\n\nRespond ONLY with valid JSON matching this schema:\n{json.dumps(schema)}"
            # Append to last user message or add to prompt
            if chat_contents and chat_contents[-1]["role"] == "user":
                chat_contents[-1]["parts"][0]["text"] += json_instruction
            else:
                user_prompt += json_instruction

        # Configure generation params
        generation_config = {
            "temperature": 0.1,  # Low temp for consistent JSON
            "max_output_tokens": max_tokens or 4096,
        }

        # Map model_size to actual models
        model_map = {
            "small": "gemini-1.5-flash-8b",
            "medium": "gemini-2.0-flash",
            "large": "gemini-2.0-flash",
        }
        actual_model = model_map.get(model_size, "gemini-2.0-flash")

        try:
            # Make the request
            response = self._client.models.generate_content(
                model=actual_model,
                contents=chat_contents,
                config=generation_config,
            )

            # Extract text from response
            text = response.text

            # Try to parse as JSON if response_model was specified
            if response_model:
                try:
                    # First try direct JSON parse
                    parsed = json.loads(text)
                    # If it's a dict with a specific key that matches response_model,
                    # wrap it appropriately
                    if isinstance(parsed, dict):
                        # Check if response_model expects a specific wrapper
                        return parsed
                    return {"response": parsed}
                except json.JSONDecodeError:
                    # Try to extract JSON from text (in case model added markdown)
                    import re

                    json_match = re.search(r"\{.*\}", text, re.DOTALL)
                    if json_match:
                        parsed = json.loads(json_match.group())
                        return parsed
                    # If all else fails, return as text - let Graphiti handle error

            return {"response": text}

        except Exception as e:
            # Return error format that Graphiti can handle
            return {"error": str(e)}

    def set_tracer(self, tracer: Any) -> None:
        """Set a tracer for logging/debugging (optional)."""
        pass


def _create_graphiti_client(uri: str, user: str, password: str) -> Graphiti:
    """Create Graphiti client with separate LLM and embedder.
    
    - LLM: OpenRouter (nvidia/nemotron-3-super-120b-a12b:free)
    - Embeddings: OpenRouter via httpx (nvidia/llama-nemotron-embed-vl-1b-v2:free)
    """
    from graphiti_core.llm_client import LLMClient, LLMConfig
    from graphiti_core.embedder.client import EmbedderClient
    import httpx

    # LLM config - OpenRouter via httpx
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    llm_model = os.environ.get("OPENROUTER_LLM_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")

    class OpenRouterLLMClient(LLMClient):
        """Custom LLM client using httpx for OpenRouter."""

        def __init__(self, api_key: str, model: str):
            config = LLMConfig(api_key=api_key, model=model)
            super().__init__(config=config)
            self._client = httpx.AsyncClient(
                base_url="https://openrouter.ai/api/v1",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=120.0,
            )
            self._model = model

        async def generate_response(
            self,
            messages: list[Any],
            response_model: type | None = None,
            max_tokens: int | None = None,
            model_size: str = "medium",
            group_id: str | None = None,
            prompt_name: str | None = None,
        ) -> dict[str, Any]:
            import json
            # Convert messages to OpenAI format
            chat_messages = []
            for msg in messages:
                if hasattr(msg, 'model_dump'):
                    msg_dict = msg.model_dump()
                elif hasattr(msg, 'dict'):
                    msg_dict = msg.dict()
                else:
                    msg_dict = msg
                role = msg_dict.get("role", "user")
                content = msg_dict.get("content", "")
                chat_messages.append({"role": role, "content": content})

            # Inject schema into prompt if response_model provided
            if response_model:
                schema = response_model.model_json_schema()
                schema_str = json.dumps(schema)
                # Append schema instruction to last user message
                for i in range(len(chat_messages) - 1, -1, -1):
                    if chat_messages[i]["role"] == "user":
                        chat_messages[i]["content"] += f"\n\nRespond ONLY with valid JSON matching this schema:\n{schema_str}"
                        break

            payload = {
                "model": self._model,
                "messages": chat_messages,
                "temperature": 0.1,
            }
            if max_tokens:
                payload["max_tokens"] = max_tokens

            try:
                response = await self._client.post("/chat/completions", json=payload)
                
                # Rate limit - try Google fallback
                if response.status_code == 429:
                    return await self._google_fallback(messages, response_model, max_tokens)
                
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]

                if response_model:
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        import re
                        match = re.search(r'\{.*\}', content, re.DOTALL)
                        if match:
                            return json.loads(match.group())
                return {"response": content}
            except Exception as e:
                # On rate limit or error, try Google fallback
                if "429" in str(e) or "rate" in str(e).lower():
                    return await self._google_fallback(messages, response_model, max_tokens)
                return {"error": str(e)}
        
        async def _google_fallback(
            self,
            messages: list[Any],
            response_model: type | None = None,
            max_tokens: int | None = None,
        ) -> dict[str, Any]:
            """Fallback to Google Gemini when OpenRouter rate limited."""
            google_key = os.environ.get("GOOGLE_API_KEY", "")
            if not google_key:
                return {"error": "OpenRouter rate limited, no Google fallback"}
            
            try:
                from google import genai
                client = genai.Client(api_key=google_key)
                
                # Convert messages
                chat_contents = []
                for msg in messages:
                    if hasattr(msg, 'model_dump'):
                        msg_dict = msg.model_dump()
                    elif hasattr(msg, 'dict'):
                        msg_dict = msg.dict()
                    else:
                        msg_dict = msg
                    role = msg_dict.get("role", "user")
                    content = msg_dict.get("content", "")
                    gemini_role = "model" if role == "assistant" else "user"
                    chat_contents.append({"role": gemini_role, "parts": [{"text": content}]})
                
                if response_model:
                    schema = response_model.model_json_schema()
                    schema_str = json.dumps(schema)
                    if chat_contents and chat_contents[-1]["role"] == "user":
                        chat_contents[-1]["parts"][0]["text"] += f"\n\nRespond ONLY with valid JSON:\n{schema_str}"
                
                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=chat_contents,
                    config={"temperature": 0.1, "max_output_tokens": max_tokens or 4096}
                )
                
                text = response.text
                if response_model:
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        import re
                        match = re.search(r'\{.*\}', text, re.DOTALL)
                        if match:
                            return json.loads(match.group())
                return {"response": text}
            except Exception as e:
                return {"error": f"Google fallback failed: {e}"}

        async def close(self):
            await self._client.aclose()

        def _generate_response(self, *args, **kwargs) -> dict[str, Any]:
            return self.generate_response(*args, **kwargs)

    llm_client = OpenRouterLLMClient(api_key=openrouter_key, model=llm_model)

    # Embedder - OpenRouter via httpx (bypasses OpenAI SDK parsing bug)
    embed_key = os.environ.get("OPENROUTER_API_KEY", "")
    
    import httpx
    
    class OpenRouterEmbedder(EmbedderClient):
        """Custom embedder using httpx for OpenRouter (bypasses SDK parsing bug)."""
        
        def __init__(self, api_key: str):
            self._client = httpx.AsyncClient(
                base_url="https://openrouter.ai/api/v1",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=60.0,
            )
            self.config = type('Config', (), {
                'embedding_model': 'nvidia/llama-nemotron-embed-vl-1b-v2:free',
                'embedding_dim': 2048,
            })()
        
        async def create(
            self, input_data: str | list[str] | list[list[int]]
        ) -> list[float]:
            if isinstance(input_data, str):
                input_data = [input_data]
            
            response = await self._client.post(
                "/embeddings",
                json={
                    "model": self.config.embedding_model,
                    "input": input_data,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]
        
        async def create_batch(
            self, input_data: list[str]
        ) -> list[list[float]]:
            if not input_data:
                return []
            
            response = await self._client.post(
                "/embeddings",
                json={
                    "model": self.config.embedding_model,
                    "input": input_data,
                },
            )
            response.raise_for_status()
            data = response.json()
            return [item["embedding"] for item in data["data"]]
        
        async def close(self):
            await self._client.aclose()
    
    embedder = OpenRouterEmbedder(api_key=embed_key)

    # Graphiti's internal OpenAIRerankerClient needs an API key -
    # reuse OpenRouter key so it can instantiate without crashing
    if openrouter_key and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = openrouter_key

    client = Graphiti(
        uri=uri,
        user=user,
        password=password,
        llm_client=llm_client,
        embedder=embedder,
    )
    return client


class SemanticMemory:
    """Graphiti-based semantic memory with Neo4j backend.

    Provides tenant isolation via group_id (tenant_id).
    Implements fallback contract: if Neo4j/Graphiti down, return empty list.
    """

    def __init__(self, tenant_id: str = "default"):
        self.tenant_id = tenant_id
        self._client: Graphiti | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._uri, self._user, self._password = _get_neo4j_config()

    def _run_async(self, coro):
        """Run a coroutine synchronously.

        Must NOT be called from within a running event loop on the same thread.
        Callers from async contexts should use asyncio.to_thread() to offload.
        """
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
        return self._loop.run_until_complete(coro)

    def available(self) -> bool:
        """Check if Graphiti is available and Neo4j is up.

        Returns True if graph is accessible, False if down.
        No exceptions raised - implements fallback contract.
        """
        if not GRAPHITI_AVAILABLE or Graphiti is None:
            return False

        # Quick direct Neo4j check first (avoids Graphiti init overhead)
        try:
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver(self._uri, auth=(self._user, self._password))
            with driver.session(database='neo4j') as session:
                result = session.run('RETURN 1 AS n')
                result.single()
            driver.close()
        except Exception:
            self._client = None
            return False

        try:
            uri = self._uri
            user = self._user
            password = self._password

            client = _create_graphiti_client(uri=uri, user=user, password=password)
            result = self._run_async(self._health_check(client))
            if not result:
                self._client = None
                return False

            self._client = client
            return True

        except Exception:
            self._client = None
            return False

    async def _health_check(self, client: Graphiti) -> bool:
        """Async health check for Graphiti connection."""
        try:
            # Try to build indices and constraints if not exists (needed for fresh DB)
            try:
                await client.build_indices_and_constraints()
            except Exception:
                # Indices might already exist, continue
                pass

            # Simple search that should return empty list (not throw) when no data
            # An empty list is a valid health result - DB is working but empty
            result = await client.search(query="__health_check__", num_results=1)
            # Return True as long as we got a list back (even if empty)
            return isinstance(result, list)
        except Exception:
            return False

    def write_episode(self, name: str, body: str) -> bool:
        """Write an episode to Graphiti for this tenant (group_id).

        Args:
            name: Episode name/identifier
            body: Episode content/body

        Returns:
            True on success, False on failure (fallback contract)
        """
        import logging
        logger = logging.getLogger(__name__)
        
        if not self.available():
            logger.warning("available() returned False")
            return False
        try:
            result = self._run_async(self._write_episode_async(name, body))
            logger.info(f"write_episode result: {result}")
            return result
        except Exception as e:
            logger.error(f"write_episode exception: {e}", exc_info=True)
            return False

    async def _write_episode_async(self, name: str, body: str) -> bool:
        """Async episode write to Graphiti."""
        if self._client is None:
            return False
        try:
            await self._client.add_episode(
                name=name,
                episode_body=body,
                source_description=body[:100],  # Use first 100 chars as description
                source=EpisodeType.text,
                reference_time=datetime.now(timezone.utc),
                group_id=self.tenant_id,
            )
            return True
        except Exception:
            return False

    def search(self, query: str, num_results: int = 5) -> list[dict]:
        """Search Graphiti for relevant episodes.

        Args:
            query: Natural language search query
            num_results: Maximum number of results (default 5)

        Returns:
            List of results as dicts. Returns empty list if graph down (fallback contract).
        """
        if not self.available():
            return []
        try:
            return self._run_async(self._search_async(query, num_results))
        except Exception:
            # Fallback contract: return empty list on any error
            return []

    async def _search_async(self, query: str, num_results: int) -> list[dict]:
        """Async search in Graphiti."""
        if self._client is None:
            return []
        try:
            results = await self._client.search(
                query=query,
                group_ids=[self.tenant_id],
                num_results=num_results,
            )
            return [
                {
                    "fact": edge.fact,
                    "valid_at": edge.valid_at.isoformat() if edge.valid_at else None,
                    "source": edge.source_node_uuid,
                    "target": edge.target_node_uuid,
                }
                for edge in results
            ]
        except Exception:
            # Fallback contract: return empty list on any error
            return []

    # Backward compatibility aliases
    def write_belief(self, tenant_id: str, topic: str, value: str, confidence: float):
        """Write a belief to semantic memory (backward compatible).
        
        Args:
            tenant_id: Tenant/workspace ID for isolation
            topic: Belief topic/subject
            value: Belief value/content
            confidence: Confidence score (0.0-1.0)
            
        Note: Sets tenant_id if different, writes as episode.
        """
        if tenant_id != self.tenant_id:
            self.tenant_id = tenant_id
        import json
        # Format as structured JSON episode
        # JSON per Anthropic talk: models less likely to overwrite JSON than Markdown
        body = json.dumps({
            "topic": topic,
            "value": value,
            "confidence": confidence,
        })
        self.write_episode(f"belief:{topic}", body)

    def query(self, cypher: str, params: dict | None = None) -> list[dict]:
        """Query semantic memory (backward compatible).
        
        Note: Graphiti uses natural language search, not Cypher.
        This method proxies to search() for compatibility.
        """
        # Strip Cypher params if provided - not used in Graphiti
        return self.search(cypher, num_results=params.get("limit", 5) if params else 5)