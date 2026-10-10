"""Mutation-testing eval harness (engine lives in src; outputs go to eval/)."""

from regtriage.eval.harness import (
    ArmScores,
    BaselineResult,
    CostRecord,
    EvalConfig,
    EvalReport,
    MeteredClient,
    SimOutcome,
    make_simulate,
    prepare_case,
    rank_files_heuristic,
    run_eval,
)
from regtriage.eval.mutants import Mutant, apply_mutant, generate_mutants
from regtriage.eval.report import (
    LIMITATIONS,
    load_eval_results,
    render_results_markdown,
    render_row_for_readme,
    summarize_manual_csv,
    write_eval_results,
)
from regtriage.eval.scoring import fabrication_rates, same_module, score_diagnosis
from regtriage.eval.upstream import (
    EVAL_MODULES,
    EVAL_TARGETS,
    UPSTREAM_LICENSE_SPDX,
    UPSTREAM_PIN,
    UPSTREAM_PIN_DATE,
    UPSTREAM_URL,
)

__all__ = [
    "ArmScores",
    "BaselineResult",
    "CostRecord",
    "EVAL_MODULES",
    "EVAL_TARGETS",
    "EvalConfig",
    "EvalReport",
    "LIMITATIONS",
    "MeteredClient",
    "Mutant",
    "SimOutcome",
    "UPSTREAM_LICENSE_SPDX",
    "UPSTREAM_PIN",
    "UPSTREAM_PIN_DATE",
    "UPSTREAM_URL",
    "apply_mutant",
    "fabrication_rates",
    "generate_mutants",
    "load_eval_results",
    "make_simulate",
    "prepare_case",
    "rank_files_heuristic",
    "render_results_markdown",
    "render_row_for_readme",
    "run_eval",
    "same_module",
    "score_diagnosis",
    "summarize_manual_csv",
    "write_eval_results",
]
