"""workflow.py — Bounded LangGraph coding-task state-machine orchestrator for JAVED.

Assembles the discrete nodes, conditional routers, loop controls, and watchdog triggers:
INTAKE -> REPOSITORY_ORIENTATION -> ROOT_CAUSE_OR_DESIGN -> PLANNING -> PLAN_GATE
-> CODING -> REVIEW -> TARGETED_TESTING -> REGRESSION_TESTING -> FINAL_REVIEW -> COMPLETED
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from javed.agent.efficiency.ledger import ActionLedger
from javed.agent.efficiency.nodes import (
    CoderNode,
    FinalReviewerNode,
    IntakeNode,
    PlanGateNode,
    PlannerNode,
    RepositoryOrientationNode,
    ReviewerNode,
    RootCauseOrDesignNode,
    TesterNode,
)
from javed.agent.efficiency.routing import (
    route_from_final_reviewer,
    route_from_plan_gate,
    route_from_reviewer,
    route_from_tester,
)
from javed.agent.efficiency.state import CodingTaskState, WorkflowState
from javed.agent.efficiency.watchdog import WatchdogEngine


class CodingWorkflowEngine:
    """Bounded, testable LangGraph workflow engine enforcing coding-agent efficiency."""

    def __init__(
        self,
        watchdog: WatchdogEngine,
        ledger: ActionLedger | None = None,
        query_fn: Callable[..., Any] | None = None,
        brief_gen_fn: Callable[..., Any] | None = None,
        plan_fn: Callable[..., Any] | None = None,
        code_fn: Callable[..., Any] | None = None,
        review_fn: Callable[..., Any] | None = None,
        test_fn: Callable[..., Any] | None = None,
        final_review_fn: Callable[..., Any] | None = None,
    ) -> None:
        self.watchdog = watchdog
        self.ledger = ledger

        # Instantiate nodes
        self.intake_node = IntakeNode()
        self.repo_node = RepositoryOrientationNode(query_fn=query_fn)
        self.brief_node = RootCauseOrDesignNode(brief_generator_fn=brief_gen_fn)
        self.planner_node = PlannerNode(plan_fn=plan_fn)
        self.plan_gate_node = PlanGateNode()
        self.coder_node = CoderNode(code_fn=code_fn)
        self.reviewer_node = ReviewerNode(review_fn=review_fn)
        self.tester_node = TesterNode(test_runner_fn=test_fn)
        self.final_reviewer_node = FinalReviewerNode(final_review_fn=final_review_fn)

        # Build StateGraph
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        builder = StateGraph(CodingTaskState)

        # Wrap nodes to pass watchdog and ledger
        def _intake(state: CodingTaskState) -> CodingTaskState:
            return self.intake_node(state, self.watchdog, self.ledger)

        def _repo(state: CodingTaskState) -> CodingTaskState:
            return self.repo_node(state, self.watchdog, self.ledger)

        def _brief(state: CodingTaskState) -> CodingTaskState:
            return self.brief_node(state, self.watchdog, self.ledger)

        def _planner(state: CodingTaskState) -> CodingTaskState:
            return self.planner_node(state, self.watchdog, self.ledger)

        def _plan_gate(state: CodingTaskState) -> CodingTaskState:
            return self.plan_gate_node(state, self.watchdog, self.ledger)

        def _coder(state: CodingTaskState) -> CodingTaskState:
            return self.coder_node(state, self.watchdog, self.ledger)

        def _reviewer(state: CodingTaskState) -> CodingTaskState:
            return self.reviewer_node(state, self.watchdog, self.ledger)

        def _tester(state: CodingTaskState) -> CodingTaskState:
            return self.tester_node(state, self.watchdog, self.ledger)

        def _final_reviewer(state: CodingTaskState) -> CodingTaskState:
            return self.final_reviewer_node(state, self.watchdog, self.ledger)

        # Register nodes
        builder.add_node("intake", _intake)
        builder.add_node("repository_orientation", _repo)
        builder.add_node("root_cause_or_design", _brief)
        builder.add_node("planner", _planner)
        builder.add_node("plan_gate", _plan_gate)
        builder.add_node("coder", _coder)
        builder.add_node("reviewer", _reviewer)
        builder.add_node("tester", _tester)
        builder.add_node("final_reviewer", _final_reviewer)

        # Normal sequential edges
        builder.add_edge(START, "intake")
        builder.add_edge("intake", "repository_orientation")
        builder.add_edge("repository_orientation", "root_cause_or_design")
        builder.add_edge("root_cause_or_design", "planner")
        builder.add_edge("planner", "plan_gate")

        # Conditional branching from Plan Gate
        builder.add_conditional_edges(
            "plan_gate",
            route_from_plan_gate,
            {
                WorkflowState.CODING.value: "coder",
                WorkflowState.REPLAN_REQUIRED.value: "planner",
                WorkflowState.SCOPE_EXPANSION_REQUIRED.value: END,
                WorkflowState.OWNER_INPUT_REQUIRED.value: END,
                WorkflowState.BUDGET_EXCEEDED.value: END,
                WorkflowState.TIMEOUT.value: END,
                WorkflowState.CANCELLED.value: END,
                WorkflowState.FAILED.value: END,
            },
        )

        builder.add_edge("coder", "reviewer")

        # Conditional branching from Reviewer
        builder.add_conditional_edges(
            "reviewer",
            route_from_reviewer,
            {
                WorkflowState.TARGETED_TESTING.value: "tester",
                WorkflowState.CODING.value: "coder",
                WorkflowState.PLANNING.value: "planner",
                WorkflowState.REPLAN_REQUIRED.value: "planner",
                WorkflowState.OWNER_INPUT_REQUIRED.value: END,
                WorkflowState.BUDGET_EXCEEDED.value: END,
                WorkflowState.CANCELLED.value: END,
                WorkflowState.FAILED.value: END,
            },
        )

        # Conditional branching from Tester
        builder.add_conditional_edges(
            "tester",
            route_from_tester,
            {
                WorkflowState.FINAL_REVIEW.value: "final_reviewer",
                WorkflowState.REGRESSION_TESTING.value: "tester",
                WorkflowState.CODING.value: "coder",
                WorkflowState.PLANNING.value: "planner",
                WorkflowState.REPLAN_REQUIRED.value: "planner",
                WorkflowState.OWNER_INPUT_REQUIRED.value: END,
                WorkflowState.BUDGET_EXCEEDED.value: END,
                WorkflowState.CANCELLED.value: END,
                WorkflowState.FAILED.value: END,
            },
        )

        # Conditional branching from Final Reviewer
        builder.add_conditional_edges(
            "final_reviewer",
            route_from_final_reviewer,
            {
                WorkflowState.COMPLETED.value: END,
                WorkflowState.OWNER_INPUT_REQUIRED.value: END,
                WorkflowState.FAILED.value: END,
                WorkflowState.CANCELLED.value: END,
            },
        )

        return builder.compile()

    def run(self, initial_state: CodingTaskState) -> CodingTaskState:
        """Execute workflow synchronously to terminal state."""
        result = self.graph.invoke(initial_state)
        # LangGraph returns dictionary or object
        if isinstance(result, dict):
            # Update fields in initial_state or return as object
            for k, v in result.items():
                if hasattr(initial_state, k):
                    setattr(initial_state, k, v)
            return initial_state
        return result
