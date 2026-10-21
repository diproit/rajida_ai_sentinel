#!/usr/bin/env python3
"""Script to generate realistic random DigiValuer webhook events and send them to Sentinel."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import time
import urllib.error
import urllib.request
import uuid

# Load secret from .env if present
def get_webhook_secret() -> str:
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


SENTINEL_WEBHOOK_URL = "http://localhost:8001/api/v1/webhooks/digivaluer"
WEBHOOK_SECRET = get_webhook_secret()

BRANCHES = [
    ("b3e945c2-192a-44e2-bca4-d19e9841f71a", "Kandy Branch"),
    ("a1f83c11-782b-43de-91c2-55d8a941f11b", "Colombo Metro Branch"),
    ("c5e221d4-883a-49bc-88b1-33e1a842f22c", "Galle Branch"),
    ("d7f994e1-221c-40ad-99f3-44c2b943f33d", "Kurunegala Branch"),
    ("e8b773a2-554d-41ca-82d4-66e3c944f44e", "Negombo Branch"),
]

VALUERS = [
    ("Sunil Perera", "0771234567", "Lanka Valuers Ltd", "VALUER"),
    ("Kithsiri Bandara", "0718822334", "Central Appraisal Co", "VALUER"),
    ("Anura Fernando", "0725566778", "Fernando & Associates", "INSURANCE_BROKER"),
    ("Chaminda Silva", "0763344556", "Southern Valuations Ltd", "FIELD_OFFICER"),
    ("Malini Jayawardena", "0779988112", "Apex Valuation Services", "BRANCH_MANAGER"),
]

SCENARIOS = [
    {
        "event_type": "UNRESPONSIVE_PARTY",
        "severity": "CRITICAL",
        "category": "VALUER_UNRESPONSIVE",
        "app_no": "MK-88A9C12E",
        "prev_status": "DRAFT",
        "new_status": "VALUATION_AND_INVESTIGATION_PROCESSING",
        "actor": "fo@mekamu.com",
        "elapsed": 7800,
        "sla": 7200,
        "delay": 600,
        "message": "Valuer Sunil Perera has not submitted a valuation report within the 2-hour SLA window.",
    },
    {
        "event_type": "SLA_DELAY_WARNING",
        "severity": "HIGH",
        "category": "BROKER_UNRESPONSIVE",
        "app_no": "MK-44F2B79A",
        "prev_status": "UNDERWRITING_REVIEW",
        "new_status": "INSURANCE_BROKER_PENDING",
        "actor": "system_sla_monitor@mekamu.com",
        "elapsed": 15200,
        "sla": 14400,
        "delay": 800,
        "message": "Insurance Broker Anura Fernando has exceeded the response threshold for policy verification.",
    },
    {
        "event_type": "STATUS_CHANGED",
        "severity": "MEDIUM",
        "category": "STATUS_TRANSITION",
        "app_no": "MK-88A9C12E",
        "prev_status": "VALUATION_AND_INVESTIGATION_PROCESSING",
        "new_status": "SITE_INSPECTION_COMPLETED",
        "actor": "valuer_portal@digivaluer.com",
        "elapsed": 8200,
        "sla": 10800,
        "delay": 0,
        "message": "Valuation inspection completed and preliminary report uploaded by Sunil Perera.",
    },
    {
        "event_type": "UNRESPONSIVE_PARTY",
        "severity": "HIGH",
        "category": "DRAFT_STAGNATION",
        "app_no": "MK-77B1D04C",
        "prev_status": "DRAFT",
        "new_status": "PENDING_CUSTOMER_DOCUMENTS",
        "actor": "dispatch@mekamu.com",
        "elapsed": 21600,
        "sla": 18000,
        "delay": 3600,
        "message": "Field Officer Chaminda Silva flagged application stalled due to missing vehicle registration copy.",
    },
    {
        "event_type": "STATUS_CHANGED",
        "severity": "LOW",
        "category": "STATUS_TRANSITION",
        "app_no": "MK-33C8E91F",
        "prev_status": "FINAL_ASSESSMENT",
        "new_status": "VALUATION_APPROVED_AND_FINALIZED",
        "actor": "branch_mgr@mekamu.com",
        "elapsed": 28800,
        "sla": 36000,
        "delay": 0,
        "message": "Senior Appraiser Malini Jayawardena approved and certified the final valuation report.",
    },
]


def build_event(scenario: dict) -> dict:
    branch_id, branch_name = random.choice(BRANCHES)
    name, phone, company, role = random.choice(VALUERS)

    event_id = str(uuid.uuid4())
    app_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    return {
        "event_id": event_id,
        "timestamp": now_iso,
        "source_system": "mekamu_mowheel",
        "environment": "production",
        "event_type": scenario["event_type"],
        "severity": scenario["severity"],
        "category": scenario["category"],
        "application": {
            "id": app_id,
            "application_no": scenario["app_no"],
            "status": scenario["new_status"],
            "branch_id": branch_id,
            "branch_name": branch_name,
            "created_at": now_iso,
            "updated_at": now_iso,
        },
        "assigned_party": {
            "role": role,
            "user_id": str(uuid.uuid4()),
            "name": name,
            "phone": phone,
            "company_name": company,
            "assigned_at": now_iso,
        },
        "metrics": {
            "elapsed_seconds": scenario["elapsed"],
            "sla_threshold_seconds": scenario["sla"],
            "delay_seconds": scenario["delay"],
        },
        "details": {
            "previous_status": scenario["prev_status"],
            "new_status": scenario["new_status"],
            "trigger_actor": scenario["actor"],
            "message": scenario["message"],
        },
    }


def send_events():
    headers = {
        "Authorization": f"Bearer {WEBHOOK_SECRET}",
        "Content-Type": "application/json",
        "User-Agent": "DigiValuer-Webhook-Simulator/1.0",
    }

    print(f"\n🚀 Dispatching {len(SCENARIOS)} simulated DigiValuer webhooks to Sentinel...")
    print(f"Endpoint: {SENTINEL_WEBHOOK_URL}")
    print(f"Secret: {WEBHOOK_SECRET[:4]}...{WEBHOOK_SECRET[-4:]}")
    print("=" * 70)

    for idx, scenario in enumerate(SCENARIOS, 1):
        event = build_event(scenario)
        print(f"\n[{idx}/{len(SCENARIOS)}] Sending {event['event_type']} ({event['severity']}) for {event['application']['application_no']}...")
        print(f"    Party: {event['assigned_party']['name']} ({event['assigned_party']['role']}) - {event['assigned_party']['company_name']}")
        print(f"    Branch: {event['application']['branch_name']}")
        print(f"    Message: {event['details']['message']}")

        req_data = json.dumps(event).encode("utf-8")
        req = urllib.request.Request(SENTINEL_WEBHOOK_URL, data=req_data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                resp_body = json.loads(resp.read().decode("utf-8"))
                print(f"    ↳ Response: HTTP {resp.status} - {resp_body.get('status')} ({resp_body.get('action_taken')})")
        except urllib.error.HTTPError as err:
            err_body = err.read().decode("utf-8")
            print(f"    ↳ ❌ HTTP Error {err.code}: {err_body}")
        except Exception as exc:
            print(f"    ↳ ❌ Failed: {exc}")

        # Small delay so SSE events stream sequentially
        time.sleep(1.5)

    print("\n" + "=" * 70)
    print("✅ All simulated DigiValuer webhook events delivered successfully!\n")


if __name__ == "__main__":
    send_events()
