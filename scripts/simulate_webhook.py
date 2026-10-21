#!/usr/bin/env python3
"""CLI utility to simulate DigiValuer webhook event dispatches to DigiValuer Sentinel."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request
import uuid


def get_default_secret() -> str:
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("DIGIVALUER_WEBHOOK_SECRET="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        return val
    return os.getenv("DIGIVALUER_WEBHOOK_SECRET", "your_webhook_signing_secret")


DEFAULT_URL = "http://localhost:8001/api/v1/webhooks/digivaluer"
DEFAULT_TOKEN = get_default_secret()


def create_payload(
    event_type: str = "STATUS_CHANGED",
    severity: str = "MEDIUM",
    category: str = "STATUS_TRANSITION",
    app_no: str = "MK-88A9C12E",
    role: str = "VALUER",
    name: str = "Sunil Perera",
    phone: str = "0771234567",
    message: str = "Valuer Sunil Perera has not submitted a valuation report within the 2-hour SLA window.",
) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_system": "mekamu_mowheel",
        "environment": "production",
        "event_type": event_type,
        "severity": severity,
        "category": category,
        "application": {
            "id": str(uuid.uuid4()),
            "application_no": app_no,
            "status": "VALUATION_AND_INVESTIGATION_PROCESSING",
            "branch_id": str(uuid.uuid4()),
            "branch_name": "Kandy Branch",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        "assigned_party": {
            "role": role,
            "user_id": str(uuid.uuid4()),
            "name": name,
            "phone": phone,
            "company_name": "Lanka Valuers Ltd",
            "assigned_at": datetime.now(timezone.utc).isoformat(),
        },
        "metrics": {
            "elapsed_seconds": 7800,
            "sla_threshold_seconds": 7200,
            "delay_seconds": 600,
        },
        "details": {
            "previous_status": "DRAFT",
            "new_status": "VALUATION_AND_INVESTIGATION_PROCESSING",
            "trigger_actor": "fo@mekamu.com",
            "message": message,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Simulate DigiValuer webhook delivery")
    parser.add_argument(
        "--type",
        choices=["STATUS_CHANGED", "UNRESPONSIVE_PARTY", "SLA_DELAY_WARNING"],
        default="UNRESPONSIVE_PARTY",
        help="Event type to dispatch",
    )
    parser.add_argument(
        "--severity",
        choices=["CRITICAL", "HIGH", "MEDIUM", "LOW"],
        default="CRITICAL",
        help="Severity rating",
    )
    parser.add_argument(
        "--app-no",
        default="MK-88A9C12E",
        help="Application number (case ID)",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help="Target Sentinel webhook endpoint",
    )
    parser.add_argument(
        "--token",
        default=DEFAULT_TOKEN,
        help="Bearer token secret",
    )
    args = parser.parse_args()

    payload = create_payload(
        event_type=args.type,
        severity=args.severity,
        category="VALUER_UNRESPONSIVE" if args.type != "STATUS_CHANGED" else "STATUS_TRANSITION",
        app_no=args.app_no,
    )

    headers = {
        "Authorization": f"Bearer {args.token}",
        "Content-Type": "application/json",
        "User-Agent": "DigiValuer-Webhook-Simulator/1.0",
    }

    print(f"\n📡 Dispatching {args.type} webhook for {args.app_no} to {args.url}...")
    print(f"Payload event_id: {payload['event_id']}")

    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(args.url, data=data_bytes, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=10.0) as response:
            resp_data = json.loads(response.read().decode("utf-8"))
            print(f"\nStatus Code: {response.status}")
            print("Response Body:")
            print(json.dumps(resp_data, indent=2))
    except urllib.error.HTTPError as err:
        print(f"\n❌ HTTP Error {err.code}: {err.read().decode('utf-8')}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"\n❌ Error dispatching webhook: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
