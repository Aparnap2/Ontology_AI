"""Database module for TrackGuard AI."""
import asyncio
import logging
import os
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from typing import Any, Dict, List

from src.config.database import get_database_url

logger = logging.getLogger(__name__)

DATABASE_URL = get_database_url("opscore")


class DB:
    _pool = None

    @classmethod
    def _get_pool(cls):
        """Lazily initialize connection pool on first use."""
        if cls._pool is None:
            try:
                cls._pool = pool.ThreadedConnectionPool(
                    minconn=2,
                    maxconn=20,
                    dsn=DATABASE_URL
                )
                logger.info("Database connection pool initialized (min=2, max=20)")
            except Exception as e:
                logger.error(f"Failed to initialize connection pool: {e}")
                raise
        return cls._pool

    @classmethod
    def close_pool(cls) -> None:
        """Gracefully close all connections in the pool."""
        if cls._pool is not None:
            cls._pool.closeall()
            cls._pool = None
            logger.info("Database connection pool closed")

    @staticmethod
    async def fetch(query: str, *args) -> List[Dict]:
        loop = asyncio.get_event_loop()
        rows = await loop.run_in_executor(None, _sync_fetch, query, args)
        return rows

    @staticmethod
    async def fetchval(query: str, *args):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_fetchval, query, args)

    @staticmethod
    async def execute(query: str, *args) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _sync_execute, query, args)


def _sync_fetch(query: str, args: tuple) -> List[Dict]:
    conn = DB._get_pool().getconn()
    conn.autocommit = True
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(query, args)
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]
    finally:
        conn.autocommit = False
        DB._get_pool().putconn(conn)


def _sync_fetchval(query: str, args: tuple):
    conn = DB._get_pool().getconn()
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute(query, args)
        row = cur.fetchone()
        cur.close()
        return row[0] if row else None
    finally:
        conn.autocommit = False
        DB._get_pool().putconn(conn)


def _sync_execute(query: str, args: tuple) -> None:
    conn = DB._get_pool().getconn()
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute(query, args)
        cur.close()
    finally:
        conn.autocommit = False
        DB._get_pool().putconn(conn)


db = DB()
