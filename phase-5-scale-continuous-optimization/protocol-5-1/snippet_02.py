class EvalOutcome(str, Enum):

    PASS = "pass"

    WARN = "warn"   # above hard floor but below soft threshold

    FAIL = "fail"

@dataclass

class EvalCase:

    case_id: str

    input_payload: dict[str, Any]

    # Set expected_fields to None for structural checks only (verifies

    # that the output is a well-formed dict). Provide a dict to enable

    # exact field-value matching against each key.

    expected_fields: dict[str, Any] | None = None

    tags: list[str] = field(default_factory=list)

@dataclass(frozen=True)

class EvalResult:

    case_id: str

    outcome: EvalOutcome

    score: float          # 0.0 to 1.0

    reason: str

    latency_ms: float

@dataclass

class EvalSuiteReport:

    suite_name: str

    results: list[EvalResult]

    @property

    def total(self) -> int:

        return len(self.results)

    @property

    def pass_rate(self) -> float:

        # WARN outcomes count as passing for the overall gate calculation.

        non_fail = sum(1 for r in self.results if r.outcome != EvalOutcome.FAIL)

        return non_fail / self.total if self.total else 0.0

    @property

    def mean_score(self) -> float:

        return sum(r.score for r in self.results) / self.total if self.total else 0.0

    def to_ci_summary(self) -> dict[str, Any]:

        by_outcome: dict[str, int] = {o.value: 0 for o in EvalOutcome}

        for r in self.results:

            by_outcome[r.outcome.value] += 1

        return {

            "suite": self.suite_name,

            "total_cases": self.total,

            "pass_rate": round(self.pass_rate, 4),

            "mean_score": round(self.mean_score, 4),

            **{f"{k}_count": v for k, v in by_outcome.items()},

        }

class DeterministicEvalRunner:

    """

    Runs a suite of deterministic eval cases against an agent callable.

    Scoring is based on structural validation and exact field matching.

    Probabilistic quality scoring via LLM-as-a-judge is handled

    separately in Protocol 5.2 through the LLMJudgeRunner class.

    """

    def __init__(

        self,

        suite_name: str,

        agent: Callable[[dict[str, Any]], dict[str, Any]],

        cases: list[EvalCase],

    ) -> None:

        self.suite_name = suite_name

        self.agent = agent

        self.cases = cases

    def run(self) -> EvalSuiteReport:

        return EvalSuiteReport(

            suite_name=self.suite_name,

            results=[self._run_case(c) for c in self.cases],

        )

    def _run_case(self, case: EvalCase) -> EvalResult:

        t0 = time.perf_counter()

        try:

            output = self.agent(case.input_payload)

        except Exception as exc:

            return EvalResult(

                case_id=case.case_id,

                outcome=EvalOutcome.FAIL,

                score=0.0,

                reason=f"agent raised {type(exc).__name__}: {exc}",

                latency_ms=0.0,

            )

        latency_ms = (time.perf_counter() - t0) * 1000

        score, reason = self._score(case, output)

        return EvalResult(

            case_id=case.case_id,

            outcome=_outcome_from_score(score),

            score=score,

            reason=reason,

            latency_ms=latency_ms,

        )

    def _score(self, case: EvalCase, actual: Any) -> tuple[float, str]:

        if not isinstance(actual, dict):

            return 0.0, f"output type is {type(actual).__name__}, expected dict"

        if case.expected_fields is None:

            return 1.0, "structural check only -- output is a well-formed dict"

        required = set(case.expected_fields)

        missing  = required - actual.keys()

        if missing:

            return 0.0, f"missing required keys: {sorted(missing)}"

        matched = sum(

            1 for k in required

            if actual.get(k) == case.expected_fields[k]

        )

        return (

            matched / len(required),

            f"{matched}/{len(required)} field values matched exactly",

        )

def _outcome_from_score(score: float) -> EvalOutcome:

    if score >= SOFT_WARN_FLOOR:

        return EvalOutcome.PASS

    if score >= HARD_PASS_FLOOR:

        return EvalOutcome.WARN

    return EvalOutcome.FAIL

def run_deterministic_gate(runner: DeterministicEvalRunner) -> None:

    """

    CI entry point. Writes a structured JSON summary to stdout and exits

    with the correct code so the pipeline gates the merge automatically.

    Call this as the final step of the deterministic eval CI stage.

    """

    report = runner.run()

    print(json.dumps(report.to_ci_summary(), indent=2))

    if report.pass_rate < HARD_PASS_FLOOR:

        print(

            f"\nCI GATE -- HARD FAIL: pass rate {report.pass_rate:.1%} "

            f"is below the required floor of {HARD_PASS_FLOOR:.1%}. "

            "Merge blocked."

        )

        sys.exit(1)

    if report.pass_rate < SOFT_WARN_FLOOR:

        print(

            f"\nCI GATE -- WARNING: pass rate {report.pass_rate:.1%} "

            f"is below the soft threshold of {SOFT_WARN_FLOOR:.1%}. "

            "Merge flagged for review. Inspect failing cases before proceeding."

        )

        # Exits 0 -- does not block the build. The warning appears in CI

        # logs and should trigger a team notification via your CI webhook.

    sys.exit(0)
