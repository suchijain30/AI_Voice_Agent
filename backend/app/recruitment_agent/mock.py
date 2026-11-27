from copy import deepcopy
from typing import Protocol

from app.recruitment_agent.schemas import RecruitmentAgentConfiguration


class AgentConfigurationConsumer(Protocol):
    """Optional capability; call providers are not required to accept this contract."""

    def prepare_agent(self, configuration: RecruitmentAgentConfiguration) -> None:
        """Validate and prepare a configuration without initiating a call."""


class MockAgentConfigurationConsumer:
    """Local-only sink for deterministic inspection. It is not an AI agent."""

    name = "mock-agent-configuration"

    def __init__(self) -> None:
        self._last_configuration: RecruitmentAgentConfiguration | None = None

    @property
    def last_configuration(self) -> RecruitmentAgentConfiguration | None:
        return deepcopy(self._last_configuration)

    def prepare_agent(self, configuration: RecruitmentAgentConfiguration) -> None:
        validated = RecruitmentAgentConfiguration.model_validate(configuration.model_dump(mode="python"))
        self._last_configuration = validated.model_copy(deep=True)
