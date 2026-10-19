import asyncio
import httpx
from sqlmodel import select

from app.db.session import async_session_maker, init_db
from app.models.agent import AgentIntervention, CommunicationChannel, InterventionStatus, RecipientRole


async def verify_dashboard_flow():
    print("=" * 80)
    print("VERIFYING DASHBOARD & INTERVENTION APPROVAL WORKFLOW")
    print("=" * 80)

    await init_db()

    # 1. Insert a fresh DRAFTED intervention for testing
    async with async_session_maker() as session:
        test_inv = AgentIntervention(
            case_id="DV-CASE-DASHBOARD-TEST",
            recipient_id="sarah.jenkins@digivaluer.example.com",
            recipient_role=RecipientRole.CASE_OWNER.value,
            stage="document_verification",
            reminder_count=1,
            drafted_message="Subject: Missing Title Deed\n\nHi Sarah, please review the missing title deed.",
            channel=CommunicationChannel.EMAIL.value,
            status=InterventionStatus.DRAFTED.value,
        )
        session.add(test_inv)
        await session.commit()
        await session.refresh(test_inv)
        target_id = test_inv.id
        print(f"1. Created test intervention in DB: ID={target_id}, Status={test_inv.status}")

    # 2. Query Dashboard API endpoints
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8001", trust_env=False) as client:
        # Check bottlenecks
        bot_res = await client.get("/api/dashboard/bottlenecks?cooling_off_hours=0")
        assert bot_res.status_code == 200
        bot_data = bot_res.json()
        print(f"2. Dashboard Bottlenecks: {bot_data['summary']['total_bottlenecks']} bottlenecks detected")
        print(f"   Stages grouped: {list(bot_data['by_stage'].keys())}")

        # Check pending interventions
        int_res = await client.get("/api/dashboard/interventions?status=DRAFTED")
        assert int_res.status_code == 200
        int_data = int_res.json()
        print(f"3. Pending Approval Queue: {int_data['summary']['drafted']} drafted reminders")

        # 3. Approve via Dashboard API endpoint (simulating user clicking 'Approve & Send' in UI)
        print(f"4. Triggering 'Approve & Send' for Intervention #{target_id}...")
        approve_res = await client.post(f"/api/dashboard/interventions/{target_id}/approve")
        assert approve_res.status_code == 200
        approve_data = approve_res.json()
        print(f"   Response status: {approve_data['intervention']['status']}")
        print(f"   Dispatched at: {approve_data['intervention']['sent_at']}")

    # 4. Verify in PostgreSQL database directly
    async with async_session_maker() as session:
        stmt = select(AgentIntervention).where(AgentIntervention.id == target_id)
        res = await session.exec(stmt)
        record = res.first()
        assert record is not None
        print("\n5. Direct PostgreSQL Database Verification:")
        print(f"   ID: {record.id}")
        print(f"   Case ID: {record.case_id}")
        print(f"   Recipient: {record.recipient_id}")
        print(f"   Channel: {record.channel}")
        print(f"   STATUS: {record.status} (Verified: Updated to SENT!)")
        print(f"   Sent At: {record.sent_at}")
        assert record.status == "SENT"
        assert record.sent_at is not None

    print("=" * 80)
    print("DASHBOARD END-TO-END APPROVAL VERIFIED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(verify_dashboard_flow())
