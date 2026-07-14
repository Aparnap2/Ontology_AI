"""CLI to trigger Self-Guardian self-checks and generate reports.

Usage:
    uv run python -m src.self_guardian.cli check --tenant-id default
    uv run python -m src.self_guardian.cli report --tenant-id default --output json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from src.self_guardian.integration import SelfGuardianIntegration


async def cmd_check(args: argparse.Namespace) -> int:
    """Run a self-check and print a summary to stdout."""
    async with SelfGuardianIntegration() as sgi:
        report = await sgi.run_self_check(tenant_id=args.tenant_id)
        print(
            f"Self-check complete: {report.total_observations} observations, "
            f"{len(report.deviations)} deviations"
        )
    return 0


async def cmd_report(args: argparse.Namespace) -> int:
    """Generate a detailed report, outputting as text or JSON."""
    async with SelfGuardianIntegration() as sgi:
        report = await sgi.run_self_check(tenant_id=args.tenant_id)

    if args.output == "json":
        print(report.model_dump_json(indent=2))
    else:
        print("=== Self-Guardian Report ===")
        print(f"Window: {report.window_start} to {report.window_end}")
        print(f"Total observations: {report.total_observations}")
        print(f"Deviations: {len(report.deviations)}")
        for dev in report.deviations:
            print(f"  [{dev.severity.upper()}] {dev.deviation.value}: {dev.description}")
        print()
        print("Agent summaries:")
        for agent, summary in report.agent_summaries.items():
            print(
                f"  {agent}: {summary['total']} ops, "
                f"{summary.get('deviations', 0)} deviations, "
                f"avg {summary.get('avg_duration_ms', 0)}ms"
            )
    return 0


def main() -> None:
    """Parse arguments and dispatch to the appropriate command handler."""
    parser = argparse.ArgumentParser(description="Self-Guardian CLI")

    subparsers = parser.add_subparsers(title="commands", dest="command")

    # --- check subcommand ---
    check_parser = subparsers.add_parser("check", help="Run a self-check")
    check_parser.add_argument(
        "--tenant-id",
        default="default",
        help="Tenant identifier (default: 'default')",
    )
    check_parser.set_defaults(func=cmd_check)

    # --- report subcommand ---
    report_parser = subparsers.add_parser("report", help="Generate a detailed report")
    report_parser.add_argument(
        "--tenant-id",
        default="default",
        help="Tenant identifier (default: 'default')",
    )
    report_parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    report_parser.set_defaults(func=cmd_report)

    args = parser.parse_args()

    if hasattr(args, "func"):
        sys.exit(asyncio.run(args.func(args)))

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
