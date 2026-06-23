from __future__ import annotations

import uuid

from dataclasses import dataclass, field

from enum import Enum

from typing import Any, Callable

class ProposalStatus(str, Enum):

    PENDING  = "pending"

    APPROVED = "approved"

    REJECTED = "rejected"

class MaintenanceTaskType(str, Enum):

    TEST_GENERATION   = "test_generation"

    SCHEMA_AUDIT      = "schema_audit"

    REGRESSION_REPORT = "regression_report"

@dataclass(frozen=True)

class CodeArtifact:

    """

    A read-only snapshot of a source file passed to a maintenance sub-agent.

    Sub-agents receive this object; they never receive a writable file handle.

    """

    file_path: str

    content: str

    language: str = "python"

@dataclass

class MaintenanceProposal:

    proposal_id: str

    task_type: MaintenanceTaskType

    source_agent_id: str

    target_artifact: str   # path of the file this proposal concerns

    proposed_output: str   # generated test cases, audit report, or diff

    rationale: str

    # These two fields enforce the core architectural constraint:

    # proposals are never auto-applied. The fields are not parameters --

    # they cannot be overridden at construction time.

    requires_human_approval: bool = field(default=True,  init=False)

    status: ProposalStatus        = field(default=ProposalStatus.PENDING, init=False)

class MaintenanceSubAgent:

    """

    Base class for all maintenance sub-agents.

    Sub-agents receive read-only CodeArtifact snapshots and return proposals.

    They have no write access to the production codebase or deployment system.

    """

    def __init__(self, agent_id: str, llm_client: Any) -> None:

        self.agent_id    = agent_id

        self.llm_client  = llm_client

    def analyze(self, artifact: CodeArtifact) -> MaintenanceProposal:

        raise NotImplementedError

class TestGeneratorAgent(MaintenanceSubAgent):

    """

    Reads the main agent's FSM or routing module and generates additional

    EvalCase definitions for branches or conditions not yet covered.

    Output is Python source ready for human review before addition to the suite.

    """

    def analyze(self, artifact: CodeArtifact) -> MaintenanceProposal:

        prompt     = self._build_generation_prompt(artifact)

        raw_output = self.llm_client.complete(prompt, max_tokens=1000)

        return MaintenanceProposal(

            proposal_id      = str(uuid.uuid4()),

            task_type        = MaintenanceTaskType.TEST_GENERATION,

            source_agent_id  = self.agent_id,

            target_artifact  = artifact.file_path,

            proposed_output  = raw_output,

            rationale        = (

                "Generated EvalCase definitions for FSM branches "

                "not represented in the current evaluation suite."

            ),

        )

    def _build_generation_prompt(self, artifact: CodeArtifact) -> str:

        return (

            f"You are a test engineer reviewing the following {artifact.language} "

            f"FSM routing module. Identify state transitions or condition branches "

            f"that have no corresponding EvalCase in the existing suite, and generate "

            f"EvalCase dataclass instantiations for each gap. "

            f"Output only valid Python -- no explanation, no markdown.\n\n"

            f"CODE:\n{artifact.content}"

        )

class MaintenanceOrchestrator:

    """

    Routes maintenance tasks to the appropriate sub-agent, collects their

    proposals, and submits every proposal for human review.

    The orchestrator never applies proposals automatically. All outputs go

    through the same HITL approval gate used for high-risk production decisions.

    Auto-applying maintenance proposals, even when the sub-agent appears

    confident, bypasses the only safety layer protecting the codebase.

    """

    def __init__(

        self,

        sub_agents: dict[MaintenanceTaskType, MaintenanceSubAgent],

        review_submission_fn: Callable[[MaintenanceProposal], None],

    ) -> None:

        self.sub_agents        = sub_agents

        self.submit_for_review = review_submission_fn

    def run_maintenance_cycle(

        self,

        artifacts: list[CodeArtifact],

        task_types: list[MaintenanceTaskType],

    ) -> list[MaintenanceProposal]:

        proposals: list[MaintenanceProposal] = []

        for artifact in artifacts:

            for task_type in task_types:

                agent = self.sub_agents.get(task_type)

                if agent is None:

                    continue

                proposal = agent.analyze(artifact)

                proposals.append(proposal)

                # Route to human review -- never to the production branch.

                # This call is not optional and has no bypass path.

                self.submit_for_review(proposal)

        return proposals
