#!/usr/bin/env python3
"""Host-path readiness gate for the Redpanda broker (issue #71 / FG-1).

The broker's admin API (port 9644) reporting "ready" only proves the broker
*process* is up. It does NOT prove a host-based client can bootstrap, resolve
the broker's ADVERTISED address, and publish. Those are separate failures:

  * docker-compose publishes 19092:9092, which LOOKS host-usable, but that
    listener advertises the container hostname "redpanda:9092", which does not
    resolve from the host. Clients bootstrap, then fail metadata resolution.
  * The EXTERNAL listener (9094) advertises "localhost:9094" and IS the host
    entrypoint.

This gate asserts the full host path, independently:

  1. bootstrap connection succeeds
  2. every advertised broker address resolves AND accepts a TCP connection
  3. a real host-originated publish is acknowledged by the broker
  4. the published message can be consumed back

Exit 0 = host path is genuinely usable. Exit 1 = not usable.
Usage: REDPANDA_URL=localhost:9094 uv run --frozen python scripts/redpanda_host_ready.py
"""
from __future__ import annotations

import asyncio
import os
import socket
import sys

BOOTSTRAP = os.environ.get("REDPANDA_URL", "localhost:9094")
TOPIC = os.environ.get("REDPANDA_READY_TOPIC", "startup_guardian.alert_delivered")
PAYLOAD = b'{"probe":"redpanda-host-ready"}'


async def main() -> int:
    try:
        from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
        from aiokafka.admin import AIOKafkaAdminClient, NewTopic
    except ImportError as exc:  # pragma: no cover
        print(f"FAIL aiokafka unavailable: {exc}")
        return 1

    # Explicit topic creation -- this gate must not rely on auto-creation.
    admin = AIOKafkaAdminClient(bootstrap_servers=BOOTSTRAP, request_timeout_ms=8000)
    try:
        await admin.start()
        try:
            await admin.create_topics([NewTopic(TOPIC, 1, 1)])
            print(f"CONFIG  topic {TOPIC!r} created explicitly")
        except Exception as exc:  # already exists
            print(f"CONFIG  topic {TOPIC!r} present ({type(exc).__name__})")
    except Exception as exc:
        print(f"FAIL 1 bootstrap via {BOOTSTRAP}: {type(exc).__name__}: {exc}")
        return 1
    finally:
        try:
            await admin.close()
        except Exception:
            pass

    producer = AIOKafkaProducer(bootstrap_servers=BOOTSTRAP, request_timeout_ms=8000)
    try:
        await producer.start()
    except Exception as exc:
        print(f"FAIL 1 bootstrap via {BOOTSTRAP}: {type(exc).__name__}: {exc}")
        return 1
    print(f"PASS 1 bootstrap connected via {BOOTSTRAP}")

    # 2. advertised addresses must resolve AND accept connections from the host
    brokers = sorted(producer.client.cluster.brokers(), key=lambda b: b.nodeId)
    if not brokers:
        print("FAIL 2 broker advertised no addresses")
        await producer.stop()
        return 1
    for broker in brokers:
        try:
            resolved = socket.gethostbyname(broker.host)
            socket.create_connection((broker.host, broker.port), 3).close()
        except Exception as exc:
            print(
                f"FAIL 2 advertised {broker.host}:{broker.port} not usable "
                f"from host: {type(exc).__name__}: {exc}"
            )
            await producer.stop()
            return 1
        print(f"PASS 2 advertised {broker.host}:{broker.port} resolves={resolved} reachable=True")

    # 3. real host-originated publish must be acknowledged
    try:
        md = await producer.send_and_wait(TOPIC, PAYLOAD)
    except Exception as exc:
        print(f"FAIL 3 publish not acknowledged: {type(exc).__name__}: {exc}")
        await producer.stop()
        return 1
    print(f"PASS 3 publish ack topic={md.topic} partition={md.partition} offset={md.offset}")
    await producer.stop()

    # 4. the message must be consumable
    consumer = AIOKafkaConsumer(
        TOPIC,
        bootstrap_servers=BOOTSTRAP,
        auto_offset_reset="earliest",
        group_id=None,
        request_timeout_ms=8000,
    )
    try:
        await consumer.start()
        found = 0
        loop = asyncio.get_event_loop()
        deadline = loop.time() + 15
        while loop.time() < deadline and found < 1:
            for _, msgs in (await consumer.getmany(timeout_ms=2000)).items():
                found += sum(1 for m in msgs if m.value == PAYLOAD)
    except Exception as exc:
        print(f"FAIL 4 consumer readback: {type(exc).__name__}: {exc}")
        try:
            await consumer.stop()
        except Exception:
            pass
        return 1
    finally:
        try:
            await consumer.stop()
        except Exception:
            pass

    if found < 1:
        print("FAIL 4 published message was not consumable")
        return 1
    print(f"PASS 4 consumer readback ({found} message)")
    print("OK redpanda host path is usable")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
