from datetime import datetime, timedelta, timezone
import logging
from typing import List, Optional
import httpx
from pydantic import BaseModel, Field

from app.core.config import get_settings

logger = logging.getLogger("services.digivaluer")
settings = get_settings()


class StakeholderContact(BaseModel):
    contact_id: str
    name: str
    email: str
    phone: Optional[str] = None
    role: str = Field(default="External Stakeholder", description="e.g. Borrower, Broker, Realtor")


class AssignedOwner(BaseModel):
    owner_id: str
    name: str
    email: str
    role: str = Field(default="Case Owner", description="e.g. Senior Appraiser, Reviewer")


class DigiValuerCase(BaseModel):
    case_id: str
    property_address: str
    property_type: str = "Residential"
    current_stage: str  # e.g., document_verification, site_inspection, comparable_analysis, final_assessment
    stage_entered_at: datetime
    last_updated_at: datetime
    assigned_owner: AssignedOwner
    stakeholder_contacts: List[StakeholderContact] = Field(default_factory=list)
    status: str = "OPEN"  # OPEN, IN_PROGRESS, STALLED, COMPLETED


class DigiValuerClient:
    """Client for interfacing with DigiValuer core API or mock valuation data."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[int] = None,
        use_mock: bool = False,
    ):
        self.base_url = (base_url or settings.DIGIVALUER_API_BASE_URL).rstrip("/")
        self.api_key = api_key or settings.DIGIVALUER_API_KEY
        self.timeout = timeout or settings.DIGIVALUER_API_TIMEOUT_SECONDS
        self.use_mock = use_mock or (not self.api_key or "example.com" in self.base_url)

    async def get_active_cases(self) -> List[DigiValuerCase]:
        """Fetch open valuation cases from DigiValuer core platform."""
        if self.use_mock:
            logger.info("DigiValuerClient using simulated mock cases")
            return self._generate_mock_cases()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": f"{settings.APP_NAME}-Client/1.0",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/cases/active", headers=headers)
                response.raise_for_status()
                data = response.json()
                cases_raw = data.get("cases", data) if isinstance(data, dict) else data
                return [DigiValuerCase.model_validate(c) for c in cases_raw]
        except Exception as exc:
            logger.warning("Failed to fetch cases from DigiValuer API (%s). Falling back to mock data.", exc)
            return self._generate_mock_cases()

    def _generate_mock_cases(self) -> List[DigiValuerCase]:
        """Generate representative mock cases across various workflow stages."""
        now = datetime.now(timezone.utc)
        return [
            # Case 1: Stagnant at document_verification (in stage 32h, SLA target is 24h)
            DigiValuerCase(
                case_id="DV-CASE-001",
                property_address="742 Evergreen Terrace, Springfield, IL",
                property_type="Single Family",
                current_stage="document_verification",
                stage_entered_at=now - timedelta(hours=32),
                last_updated_at=now - timedelta(hours=32),
                assigned_owner=AssignedOwner(
                    owner_id="usr_01",
                    name="Sarah Jenkins",
                    email="s.jenkins@digivaluer.example.com",
                ),
                stakeholder_contacts=[
                    StakeholderContact(
                        contact_id="stk_01",
                        name="Homer Simpson",
                        email="homer@springfield.net",
                        role="Borrower",
                    ),
                    StakeholderContact(
                        contact_id="stk_02",
                        name="Lionel Hutz",
                        email="hutz@lawspringfield.com",
                        role="Closing Attorney",
                    ),
                ],
                status="OPEN",
            ),
            # Case 2: Active on-track at site_inspection (in stage 8h, SLA target is 48h)
            DigiValuerCase(
                case_id="DV-CASE-002",
                property_address="124 Conch Street, Bikini Bottom, OC",
                property_type="Waterfront Residential",
                current_stage="site_inspection",
                stage_entered_at=now - timedelta(hours=8),
                last_updated_at=now - timedelta(hours=8),
                assigned_owner=AssignedOwner(
                    owner_id="usr_02",
                    name="Edward Tentacles",
                    email="e.tentacles@digivaluer.example.com",
                ),
                stakeholder_contacts=[
                    StakeholderContact(
                        contact_id="stk_03",
                        name="Eugene Krabs",
                        email="krabs@krustykrab.biz",
                        role="Property Owner",
                    )
                ],
                status="IN_PROGRESS",
            ),
            # Case 3: Stalled at final_assessment (in stage 28h, SLA target is 24h, warning is 20h)
            DigiValuerCase(
                case_id="DV-CASE-003",
                property_address="221B Baker Street, London, UK",
                property_type="Multi-Family Townhouse",
                current_stage="final_assessment",
                stage_entered_at=now - timedelta(hours=28),
                last_updated_at=now - timedelta(hours=28),
                assigned_owner=AssignedOwner(
                    owner_id="usr_03",
                    name="John Watson",
                    email="j.watson@digivaluer.example.com",
                ),
                stakeholder_contacts=[
                    StakeholderContact(
                        contact_id="stk_04",
                        name="Martha Hudson",
                        email="m.hudson@bakerstreet.co.uk",
                        role="Landlord",
                    )
                ],
                status="OPEN",
            ),
        ]


def get_digivaluer_client() -> DigiValuerClient:
    """Dependency provider for DigiValuerClient."""
    return DigiValuerClient()
