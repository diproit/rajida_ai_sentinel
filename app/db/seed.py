import asyncio
import logging
from sqlmodel import select

from app.db.session import async_session_maker, init_db
from app.models.agent import CaseSLAConfig, EscalationRule

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed")

# Default SLA configurations for standard valuation workflow stages
DEFAULT_SLA_CONFIGS = [
    {
        "stage_id": "document_verification",
        "stage_name": "Document Verification",
        "target_duration_hours": 24.0,
        "critical_warning_threshold_hours": 18.0,
    },
    {
        "stage_id": "site_inspection",
        "stage_name": "Site Inspection",
        "target_duration_hours": 48.0,
        "critical_warning_threshold_hours": 36.0,
    },
    {
        "stage_id": "comparable_analysis",
        "stage_name": "Comparable Market Analysis",
        "target_duration_hours": 24.0,
        "critical_warning_threshold_hours": 18.0,
    },
    {
        "stage_id": "final_assessment",
        "stage_name": "Final Assessment & Quality Review",
        "target_duration_hours": 24.0,
        "critical_warning_threshold_hours": 20.0,
    },
]

# Default escalation rules corresponding to valuation stages
DEFAULT_ESCALATION_RULES = [
    {
        "stage_id": "document_verification",
        "max_reminders": 2,
        "escalation_target_role": "Senior Reviewer",
    },
    {
        "stage_id": "site_inspection",
        "max_reminders": 3,
        "escalation_target_role": "Field Appraisal Lead",
    },
    {
        "stage_id": "comparable_analysis",
        "max_reminders": 2,
        "escalation_target_role": "Senior Valuation Specialist",
    },
    {
        "stage_id": "final_assessment",
        "max_reminders": 2,
        "escalation_target_role": "Chief Appraiser",
    },
]


async def seed_database() -> None:
    """Initialize tables and seed default SLA configurations and escalation rules."""
    logger.info("Initializing database schema...")
    await init_db()

    async with async_session_maker() as session:
        # Seed Case SLA Configurations
        logger.info("Seeding Case SLA Configurations...")
        for cfg in DEFAULT_SLA_CONFIGS:
            statement = select(CaseSLAConfig).where(CaseSLAConfig.stage_id == cfg["stage_id"])
            result = await session.exec(statement)
            existing = result.first()

            if existing:
                logger.info("Updating existing SLA config for stage '%s'", cfg["stage_id"])
                existing.stage_name = cfg["stage_name"]
                existing.target_duration_hours = cfg["target_duration_hours"]
                existing.critical_warning_threshold_hours = cfg["critical_warning_threshold_hours"]
                session.add(existing)
            else:
                logger.info("Inserting new SLA config for stage '%s'", cfg["stage_id"])
                new_sla = CaseSLAConfig(**cfg)
                session.add(new_sla)

        # Seed Escalation Rules
        logger.info("Seeding Escalation Rules...")
        for rule in DEFAULT_ESCALATION_RULES:
            statement = select(EscalationRule).where(EscalationRule.stage_id == rule["stage_id"])
            result = await session.exec(statement)
            existing_rule = result.first()

            if existing_rule:
                logger.info("Updating existing escalation rule for stage '%s'", rule["stage_id"])
                existing_rule.max_reminders = rule["max_reminders"]
                existing_rule.escalation_target_role = rule["escalation_target_role"]
                session.add(existing_rule)
            else:
                logger.info("Inserting new escalation rule for stage '%s'", rule["stage_id"])
                new_rule = EscalationRule(**rule)
                session.add(new_rule)

        await session.commit()
        logger.info("Database seeding completed successfully.")


if __name__ == "__main__":
    asyncio.run(seed_database())
