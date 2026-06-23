from enum import Enum

from fastapi import FastAPI, HTTPException

from pydantic import BaseModel, Field

app = FastAPI()

class AgentRole(str, Enum):

    SUPPORT_AGENT = "SUPPORT_AGENT"

    FINANCE_WORKER = "FINANCE_WORKER"

class AgentIdentity(BaseModel):

    # NOTE: this object represents an identity that has already been

    # authenticated. It is never trusted raw from the request body in

    # production. The orchestrator decodes it from a signed token

    # (see clarification below) before this model is ever instantiated.

    agent_id: str = Field(..., description="Unique cryptographic identifier")

    role: AgentRole = Field(..., description="Statically assigned RBAC role")

    session_id: str = Field(..., description="Traceable session execution ID")

class ToolExecutionRequest(BaseModel):

    identity: AgentIdentity

    # payload schema omitted for brevity

def enforce_role_boundary(identity: AgentIdentity, required_role: AgentRole):

    """Deterministic interceptor. Kills execution if authorization fails."""

    if identity.role != required_role:

        raise HTTPException(

            status_code=403,

            detail=f"FATAL: Agent {identity.agent_id} lacks {required_role} role."

        )

@app.post("/tools/execute_refund")

async def execute_refund_tool(request: ToolExecutionRequest):

    # 1. Intercept and evaluate passport BEFORE any business logic runs

    enforce_role_boundary(request.identity, AgentRole.FINANCE_WORKER)

    # 2. Deterministic wall passed. Safe to touch external financial API.

    # stripe_client.refunds.create(...)

    return {

        "status": "success",

        "audited_by_agent": request.identity.agent_id,

        "session_trace": request.identity.session_id

    }
