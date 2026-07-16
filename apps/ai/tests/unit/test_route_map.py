"""Tests for OntologyAI V5.1 route map (PRD §25).

Asserts @mention aliases route to the correct workflow class.
Run:
    cd /home/aparna/Desktop/iterate_swarm/apps/ai
    uv run pytest tests/unit/test_route_map.py -v
"""
import pytest

from src.workflows import ROUTE_MAP


def _class(name):
    from src.workflows import WORKFLOW_REGISTRY
    return WORKFLOW_REGISTRY[name]


class TestRouteMap:
    def test_default_routes_to_chief_of_staff(self):
        for alias in ["@ontologyai", "@agent", "@ask", "@chief"]:
            assert ROUTE_MAP[alias] is _class("ChiefOfStaffWorkflow"), alias

    def test_specialist_aliases(self):
        assert ROUTE_MAP["@discover"] is _class("DiscoveryWorkflow")
        assert ROUTE_MAP["@map"] is _class("OntologyMappingWorkflow")
        assert ROUTE_MAP["@truth"] is _class("TruthAnalysisWorkflow")
        assert ROUTE_MAP["@build"] is _class("WorkflowBuilderWorkflow")
        assert ROUTE_MAP["@govern"] is _class("GovernanceWorkflow")

    def test_sarthi_backward_compat(self):
        assert ROUTE_MAP["@sarthi"] is _class("ChiefOfStaffWorkflow")

    def test_all_routes_resolve_to_registered_workflows(self):
        for alias, wf_cls in ROUTE_MAP.items():
            assert wf_cls in {
                v for v in __import__(
                    "src.workflows", fromlist=["WORKFLOW_REGISTRY"]
                ).WORKFLOW_REGISTRY.values()
            }
