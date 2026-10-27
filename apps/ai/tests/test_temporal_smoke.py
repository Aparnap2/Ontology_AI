"""Temporal Smoke Test — verifies connectivity to the real Temporal server.

Phase: INTEGRATION (real Temporal server, no Docker gate needed)
"""

from __future__ import annotations

import pytest
from temporalio.client import Client
from temporalio.api.workflowservice.v1 import (
    DescribeNamespaceRequest,
    ListNamespacesRequest,
)

TEMPORAL_ADDRESS = "localhost:7233"
TEMPORAL_NAMESPACE = "default"


@pytest.mark.asyncio
async def test_temporal_connection():
    """Can connect to Temporal on localhost:7233 and describe the default namespace."""
    client = await Client.connect(TEMPORAL_ADDRESS, namespace=TEMPORAL_NAMESPACE)
    req = DescribeNamespaceRequest(namespace=TEMPORAL_NAMESPACE)
    ns = await client.workflow_service.describe_namespace(req)
    assert ns.namespace_info.name == "default"


@pytest.mark.asyncio
async def test_temporal_list_namespaces():
    """Can list namespaces on the Temporal server."""
    client = await Client.connect(TEMPORAL_ADDRESS, namespace=TEMPORAL_NAMESPACE)
    req = ListNamespacesRequest()
    result = await client.workflow_service.list_namespaces(req)
    names = [ns.namespace_info.name for ns in result.namespaces]
    assert "default" in names
    assert len(names) >= 1
