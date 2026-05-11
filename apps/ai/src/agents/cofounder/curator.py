"""Curator: ACE Curator for playbook updates.

Updates Graphiti playbook with incremental confidence updates.
PRD Reference: Section 260
"""
from dataclasses import dataclass
from typing import Optional

from src.memory.semantic import SemanticMemory


@dataclass
class PlaybookUpdate:
    domain: str
    strategy: str
    old_confidence: float
    new_confidence: float
    evidence_count: int


class Curator:
    """ACE Curator: updates playbook confidence."""
    
    def __init__(self, tenant_id: str = "default"):
        self.tenant_id = tenant_id
        self._memory = SemanticMemory(tenant_id=tenant_id)
    
    def update(
        self,
        domain: str,
        strategy: str,
        score_delta: float,
        evidence_count: int = 1,
    ) -> PlaybookUpdate:
        """Update playbook confidence.
        
        Args:
            domain: Domain (finance/bi/ops)
            strategy: Strategy description
            score_delta: Confidence adjustment
            evidence_count: Number of evidence points
            
        Returns:
            PlaybookUpdate with old/new confidence
        """
        # Get current confidence from Graphiti
        current_confidence = self._fetch_current_confidence(domain, strategy)
        
        # Calculate new confidence
        new_confidence = max(0.0, min(1.0, current_confidence + score_delta))
        old_confidence = current_confidence
        
        # Write updated playbook to Graphiti
        playbook_entry = (
            f"domain: {domain}\n"
            f"strategy: {strategy}\n"
            f"confidence: {new_confidence}\n"
            f"evidence_count: {evidence_count}\n"
        )
        
        self._memory.write_episode(
            name=f"playbook:{domain}:{strategy}",
            body=playbook_entry,
        )
        
        return PlaybookUpdate(
            domain=domain,
            strategy=strategy,
            old_confidence=old_confidence,
            new_confidence=new_confidence,
            evidence_count=evidence_count,
        )
    
    def _fetch_current_confidence(
        self,
        domain: str,
        strategy: str,
    ) -> float:
        """Fetch current confidence from Graphiti."""
        try:
            results = self._memory.search(
                query=f"playbook {domain} {strategy}",
                num_results=1,
            )
            if results:
                # Parse confidence from result
                body = results[0].get("fact", "")
                for line in body.split("\n"):
                    if line.startswith("confidence:"):
                        return float(line.split(":")[1].strip())
        except Exception:
            pass
        
        # Default: return 1.0 for new strategies
        return 1.0


def update_playbook(
    tenant_id: str,
    domain: str,
    strategy: str,
    score_delta: float,
    evidence_count: int = 1,
) -> PlaybookUpdate:
    """Convenience function for updating playbook."""
    curator = Curator(tenant_id=tenant_id)
    return curator.update(domain, strategy, score_delta, evidence_count)


@dataclass
class ConfidenceUpdateResult:
    success: bool
    tenant_id: str
    domain: str
    confidence_delta: float
    new_confidence: float | None = None
    error: str | None = None


def update_strategy_confidence(
    tenant_id: str,
    domain: str,
    feedback_type: str,
    score: float,
) -> ConfidenceUpdateResult:
    """Update Graphiti Strategy confidence score based on founder feedback."""
    score_map = {
        "acknowledged": 1.0,
        "acted_on": 1.5,
        "ignored": -0.5,
        "disputed": -1.0,
        "dismissed": -1.5,
    }
    delta = score_map.get(feedback_type, score)

    try:
        from src.memory.semantic import SemanticMemory

        memory = SemanticMemory(tenant_id=tenant_id)
        playbook_entry = (
            f"domain: {domain}\n"
            f"strategy: confidence_update\n"
            f"confidence_delta: {delta}\n"
            f"feedback_type: {feedback_type}\n"
        )
        memory.write_episode(
            name=f"strategy_confidence:{domain}",
            body=playbook_entry,
        )
        return ConfidenceUpdateResult(
            success=True,
            tenant_id=tenant_id,
            domain=domain,
            confidence_delta=delta,
            new_confidence=delta,
        )
    except Exception as e:
        return ConfidenceUpdateResult(
            success=False,
            tenant_id=tenant_id,
            domain=domain,
            confidence_delta=delta,
            error=str(e),
        )