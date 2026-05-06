"""
OpenTelemetry tracing initialization for Python services.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def get_otlp_endpoint() -> str:
    """Get OTel Collector endpoint from environment or default."""
    if endpoint := os.getenv("OTEL_COLLECTOR_HOST"):
        return f"{endpoint}:4317"
    return "localhost:4317"


def get_service_name(default: str = "python-service") -> str:
    """Get service name from environment or use default."""
    return os.getenv("OTEL_SERVICE_NAME", default)


def init_tracing(
    service_name: Optional[str] = None,
    endpoint: Optional[str] = None,
    enabled: bool = True,
) -> Optional[object]:
    """
    Initialize OpenTelemetry tracing.
    
    Args:
        service_name: Name of the service (auto-detected from env)
        endpoint: OTel Collector endpoint (auto-detected from env)
        enabled: Whether to enable tracing (default: True)
        
    Returns:
        TracerProvider if successful, None otherwise
    """
    if not enabled:
        logger.info("Tracing disabled")
        return None
    
    service = service_name or get_service_name()
    endpoint = endpoint or get_otlp_endpoint()
    
    try:
        # OTel imports
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME
        
        # Create OTLP exporter
        exporter = OTLPSpanExporter(
            endpoint=endpoint,
            insecure=True,
        )
        
        # Create resource with service name
        resource = Resource.create({
            SERVICE_NAME: service,
        })
        
        # Create provider with resource
        provider = TracerProvider(resource=resource)
        
        # Add batch processor with exporter
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)
        
        # Set global provider
        trace.set_tracer_provider(provider)
        
        logger.info(f"OTel tracing initialized: service={service} endpoint={endpoint}")
        return provider
        
    except Exception as e:
        logger.warning(f"Failed to initialize tracing: {e}")
        return None


def get_tracer(name: Optional[str] = None) -> Optional[object]:
    """
    Get a tracer for manual instrumentation.
    
    Args:
        name: Tracer name (defaults to service name)
        
    Returns:
        Tracer instance or None if not initialized
    """
    try:
        from opentelemetry import trace
        service = get_service_name()
        return trace.get_tracer(name or service)
    except Exception:
        return None


__all__ = [
    "init_tracing",
    "get_tracer",
    "get_service_name",
    "get_otlp_endpoint",
]