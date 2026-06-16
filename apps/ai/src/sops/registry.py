"""
SOP Registry for TrackGuard SOP Runtime.

All SOPs self-register via register() function.
"""
from __future__ import annotations
from src.sops.base import BaseSOP


# Global registry of all SOPs
_REGISTRY: dict[str, BaseSOP] = {}


def register(sop: BaseSOP) -> None:
    """
    Register an SOP instance.

    Usage:
        from src.sops.base import BaseSOP, SOPResult

        class MySOP(BaseSOP):
            sop_name = "SOP_MY_SOP"
            async def execute(self, payload_ref: str, founder_id: str) -> SOPResult:
                ...

        register(MySOP())
    """
    _REGISTRY[sop.sop_name] = sop


class SOPRegistry:
    """
    Registry for accessing registered SOPs.

    Usage:
        registry = SOPRegistry()
        if registry.has("SOP_REVENUE_RECEIVED"):
            sop = registry.get("SOP_REVENUE_RECEIVED")
            result = await sop.execute(payload_ref, founder_id)
    """

    def has(self, sop_name: str) -> bool:
        """Check if SOP is registered."""
        return sop_name in _REGISTRY

    def get(self, sop_name: str) -> BaseSOP:
        """
        Get registered SOP by name.

        Args:
            sop_name: Name of SOP (e.g., "SOP_REVENUE_RECEIVED")

        Returns:
            Registered SOP instance

        Raises:
            KeyError: If SOP not registered
        """
        if sop_name not in _REGISTRY:
            raise KeyError(
                f"No executor for '{sop_name}'. "
                f"Registered SOPs: {sorted(_REGISTRY.keys())}"
            )
        return _REGISTRY[sop_name]

    def all(self) -> list[str]:
        """Return list of all registered SOP names."""
        return sorted(_REGISTRY.keys())

    def count(self) -> int:
        """Return count of registered SOPs."""
        return len(_REGISTRY)


# Auto-import all SOPs so they self-register
# This will be populated as SOPs are implemented in Phase 8-10
def _load_all() -> None:
    """Load and register all SOPs."""
    # Import SOPs as they are implemented
    from src.sops import revenue_received  # Phase 8
    from src.sops import bank_statement_ingest  # Phase 9
    from src.sops import weekly_briefing  # Phase 10


# Initialize registry on module load
_load_all()
