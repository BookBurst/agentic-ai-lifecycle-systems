# Agentic AI Lifecycle Systems — Official Code Blueprints

Welcome.

This is the official code repository for the book **"Agentic AI Lifecycle Systems"** by Isaac Vance.
It contains every code blueprint from the book, ready to copy and paste, organized exactly the way the
book is: **5 lifecycle phases**, each split into the individual **protocols** you read chapter by chapter.

> 📖 *Amazon link: coming soon.*

---

## 🛠 How to Use These Blueprints

You are the architect, not the typist. To deploy the patterns from any chapter:

1. **Locate the phase folder** matching the part of the book you are reading.
2. **Open the protocol sub-folder** (e.g. `protocol-2-1`) for that specific chapter.
3. **Copy the snippet** you need (`.py` for Python, `.sql` for database schemas).
4. **Paste it** into your project, into ChatGPT / Gemini / Claude, or run it directly.

Each file is self-contained and named `snippet_NN`. Files are numbered in the order they appear in the book.

---

## ⚙️ Setup

```bash
# 1. Clone the repository
git clone https://github.com/BookBurst/agentic-ai-lifecycle-systems.git
cd agentic-ai-lifecycle-systems

# 2. (Recommended) create a virtual environment
python -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate

# 3. Install the dependencies
pip install -r requirements.txt

# 4. Configure your secrets
cp .env.example .env             # then edit .env with your real keys
```

> ⚠️ **Security:** rename `.env.example` to `.env` and insert your personal API keys and database URLs.
> Your real `.env` file is already git-ignored. **Never share it publicly.**

---

## 📂 Repository Structure

### Phase 1 — Identity Design & Governance

Cryptographic identity, least-privilege RBAC, trust boundaries and narrow scoping.

- **Protocol 1.1 — Agent Identity Governance & Least Privilege** &nbsp;→&nbsp; `phase-1-identity-design-governance/protocol-1-1/`  
  `snippet_01.py`
- **Protocol 1.2 — Trust Boundaries & Multi-Tenant Architecture** &nbsp;→&nbsp; `phase-1-identity-design-governance/protocol-1-2/`  
  `snippet_01.py`
- **Protocol 1.3 — Defining Scope (Narrow Scoping)** &nbsp;→&nbsp; `phase-1-identity-design-governance/protocol-1-3/`  
  `snippet_01.py`

### Phase 2 — Build & Behavioral Engineering

Finite-state orchestration, PromptOps, supervisor-worker routing, memory and multi-model cost control.

- **Protocol 2.1 — Orchestrating Through FSM & Graphs (DAG)** &nbsp;→&nbsp; `phase-2-build-behavioral-engineering/protocol-2-1/`  
  `snippet_01.py`, `snippet_02.py`
- **Protocol 2.2 — PromptOps & Stage Pinning** &nbsp;→&nbsp; `phase-2-build-behavioral-engineering/protocol-2-2/`  
  `snippet_01.py`, `snippet_02.py`
- **Protocol 2.3 — Supervisor-Worker Pattern (Hierarchical Routing)** &nbsp;→&nbsp; `phase-2-build-behavioral-engineering/protocol-2-3/`  
  `snippet_01.py`, `snippet_02.py`
- **Protocol 2.4 — Memory Infrastructure & Salience Resolution** &nbsp;→&nbsp; `phase-2-build-behavioral-engineering/protocol-2-4/`  
  `snippet_01.py`, `snippet_02.sql`, `snippet_03.py`, `snippet_04.py`
- **Protocol 2.5 — Multi-Model Routing & Cost-Aware Task Allocation** &nbsp;→&nbsp; `phase-2-build-behavioral-engineering/protocol-2-5/`  
  `snippet_01.py`, `snippet_02.py`

### Phase 3 — Deploy & Idempotency

Idempotency, write-ahead intent logs, saga rollbacks, context-window lifecycle and zero-downtime migrations.

- **Protocol 3.1 — Absolute Idempotency** &nbsp;→&nbsp; `phase-3-deploy-idempotency/protocol-3-1/`  
  `snippet_01.py`, `snippet_02.sql`, `snippet_03.py`
- **Protocol 3.2 — The Write-Ahead Log of Intent** &nbsp;→&nbsp; `phase-3-deploy-idempotency/protocol-3-2/`  
  `snippet_01.sql`, `snippet_02.py`, `snippet_03.py`
- **Protocol 3.3 — Deterministic Rollback (Saga Pattern)** &nbsp;→&nbsp; `phase-3-deploy-idempotency/protocol-3-3/`  
  `snippet_01.py`
- **Protocol 3.4 — Context Window Lifecycle Management** &nbsp;→&nbsp; `phase-3-deploy-idempotency/protocol-3-4/`  
  `snippet_01.py`, `snippet_02.py`
- **Protocol 3.5 — Agent Version Migration & Zero-Downtime Upgrades** &nbsp;→&nbsp; `phase-3-deploy-idempotency/protocol-3-5/`  
  `snippet_01.py`, `snippet_02.py`, `snippet_03.sql`

### Phase 4 — Operate & Runtime Governance

Structured-output enforcement, forensic telemetry, human-in-the-loop gates, active security and high availability.

- **Protocol 4.1 — Enforcing Structured Outputs** &nbsp;→&nbsp; `phase-4-operate-runtime-governance/protocol-4-1/`  
  `snippet_01.py`, `snippet_02.py`
- **Protocol 4.2 — Forensic Telemetry & Financial Circuit Breakers** &nbsp;→&nbsp; `phase-4-operate-runtime-governance/protocol-4-2/`  
  `snippet_01.py`, `snippet_02.py`, `snippet_03.sql`, `snippet_04.sql`, `snippet_05.py`, `snippet_06.sql`, `snippet_07.sql`
- **Protocol 4.3 — Pause & Resume (Human-in-the-Loop)** &nbsp;→&nbsp; `phase-4-operate-runtime-governance/protocol-4-3/`  
  `snippet_01.py`
- **Protocol 4.4 — Active Security & the Semantic Hypervisor** &nbsp;→&nbsp; `phase-4-operate-runtime-governance/protocol-4-4/`  
  `snippet_01.py`
- **Protocol 4.5 — High Availability & Agent State Resilience** &nbsp;→&nbsp; `phase-4-operate-runtime-governance/protocol-4-5/`  
  `snippet_01.py`, `snippet_02.py`, `snippet_03.py`

### Phase 5 — Scale & Continuous Optimization

Evaluation-driven development, component-level evaluation and self-referential SDLC automation.

- **Protocol 5.1 — Hybrid Testing & Evaluation-Driven Development** &nbsp;→&nbsp; `phase-5-scale-continuous-optimization/protocol-5-1/`  
  `snippet_01.py`, `snippet_02.py`, `snippet_03.py`, `snippet_04.py`
- **Protocol 5.2 — Component-Level Evaluation** &nbsp;→&nbsp; `phase-5-scale-continuous-optimization/protocol-5-2/`  
  `snippet_01.py`
- **Protocol 5.3 — SDLC Automation via Self-Referential Systems** &nbsp;→&nbsp; `phase-5-scale-continuous-optimization/protocol-5-3/`  
  `snippet_01.py`

---

## 📝 Notes

- **Python files** are syntactically validated. Some snippets are intentionally partial (they build on classes
  defined in an earlier protocol of the same phase), exactly as presented in the book.
- **SQL files** contain the PostgreSQL schemas (`CREATE TABLE` / `CREATE INDEX`) and reporting queries referenced in the text.
- Dependencies are listed in `requirements.txt`; environment variables in `.env.example`.

---

*Stop typing. Start architecting.*
