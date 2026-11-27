from uuid import UUID

from sqlalchemy.orm import Session

from app.recruitment_agent.builder import RecruitmentAgentConfigurationBuilder
from app.recruitment_agent.mock import AgentConfigurationConsumer
from app.recruitment_agent.schemas import RecruitmentAgentConfiguration


class RecruitmentAgentPreparationService:
    """Compose the existing-data builder with an explicitly supplied offline consumer."""

    def __init__(self, db: Session, consumer: AgentConfigurationConsumer):
        self.builder = RecruitmentAgentConfigurationBuilder(db)
        self.consumer = consumer

    def prepare(
        self,
        candidate_id: UUID,
        session_id: UUID,
        *,
        include_phone: bool = False,
    ) -> RecruitmentAgentConfiguration:
        configuration = self.builder.build(candidate_id, session_id, include_phone=include_phone)
        self.consumer.prepare_agent(configuration)
        return configuration
