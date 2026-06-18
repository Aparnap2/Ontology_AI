"""Main entry point for the AI service.

This module supports running:
1. Temporal worker (default) - listens to AI_TASK_QUEUE
2. gRPC server - serves gRPC requests from Go core
3. APScheduler-based jobs (alternative to Temporal)
4. Both services concurrently
"""

import asyncio
import logging
import os
import sys
from concurrent import futures

import structlog
import grpc
from temporalio.client import Client
from temporalio.worker import Worker

from src.activities import analyze_feedback
from src.config import get_config
from src.config.logging import setup_logging
from src.grpc_server import serve as start_grpc_server, AgentServicer

USE_SCHEDULER = os.environ.get("USE_APSCHEDULER", "false").lower() == "true"
if USE_SCHEDULER:
    from src.scheduler import (
        register_tenant_schedules,
        start_scheduler,
        shutdown_scheduler,
    )

import os as _os
_PROTO_PATH = _os.path.join(_os.path.dirname(__file__), '..', '..', '..', 'gen', 'python')
sys.path.insert(0, _PROTO_PATH)
import ai.v1.agent_pb2_grpc as pb2_grpc

logger = structlog.get_logger(__name__)


async def run_temporal_worker():
    """Run the Temporal worker for AI activities."""
    config = get_config()
    logger.info("Starting Temporal Worker", address=config.temporal.address, task_queue=config.temporal.task_queue)
    client = await Client.connect(target=config.temporal.address, namespace=config.temporal.namespace)
    worker = Worker(client, task_queue=config.temporal.task_queue, activities=[analyze_feedback])
    logger.info("Temporal Worker started, waiting for tasks...")
    await worker.run()


async def run_grpc_server(port: str = "[::]:50051"):
    """Run the gRPC server."""
    logger.info(f"Starting gRPC server on {port}")
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    pb2_grpc.add_AgentServiceServicer_to_server(AgentServicer(), server)
    server.add_insecure_port(port)
    await server.start()
    logger.info("gRPC server started successfully")
    await server.wait_for_termination()


async def run_both(grpc_port: str = "[::]:50051"):
    """Run both Temporal worker and gRPC server concurrently."""
    await asyncio.gather(run_temporal_worker(), run_grpc_server(grpc_port))


def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="IterateSwarm AI Service")
    parser.add_argument("--mode", choices=["temporal", "grpc", "both"], default="both")
    parser.add_argument("--grpc-port", default="[::]:50051")
    return parser.parse_args()


async def bootstrap_scheduler():
    """Bootstrap APScheduler runtime."""
    logger.info("Bootstrapping APScheduler runtime")
    tenants = [t.strip() for t in os.environ.get("ACTIVE_TENANTS", "default").split(",") if t.strip()]
    logger.info(f"Loading {len(tenants)} tenants")
    for tenant_id in tenants:
        register_tenant_schedules(tenant_id)
    start_scheduler()
    logger.info("APScheduler runtime started")


def main():
    args = parse_args()
    setup_logging()
    log = structlog.get_logger()
    log.info("Starting IterateSwarm AI Service", mode=args.mode, use_scheduler=USE_SCHEDULER)

    async def run_with_scheduler():
        tasks = []
        try:
            if USE_SCHEDULER:
                await bootstrap_scheduler()
            if args.mode in ("temporal", "both"):
                tasks.append(asyncio.create_task(run_temporal_worker()))
            if args.mode in ("grpc", "both"):
                tasks.append(asyncio.create_task(run_grpc_server(args.grpc_port)))
            if tasks:
                await asyncio.gather(*tasks)
        finally:
            if USE_SCHEDULER:
                shutdown_scheduler()

    try:
        if USE_SCHEDULER:
            asyncio.run(run_with_scheduler())
        elif args.mode == "temporal":
            asyncio.run(run_temporal_worker())
        elif args.mode == "grpc":
            asyncio.run(run_grpc_server(args.grpc_port))
        else:
            asyncio.run(run_with_scheduler())
    except KeyboardInterrupt:
        log.info("Service shutting down...")
    except Exception as e:
        log.error("Service error", error=str(e))
        raise


if __name__ == "__main__":
    main()