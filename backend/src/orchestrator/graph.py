from typing import Optional
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from src.orchestrator.nodes import (
    complete_interview,
    inject_guidance,
    mark_problem_discussed,
    present_problem,
    record_question,
    route_event,
    transition_stage,
)
from src.orchestrator.state import InterviewState


def build_interview_graph(
    checkpointer: Optional[BaseCheckpointSaver] = None,
):
    """Build and compile the authoritative event-driven interview state graph."""
    workflow = StateGraph(InterviewState)

    # 1. Add router and state mutation nodes
    workflow.add_node("route_event", route_event)
    workflow.add_node("record_question", record_question)
    workflow.add_node("inject_guidance", inject_guidance)
    workflow.add_node("present_problem", present_problem)
    workflow.add_node("mark_problem_discussed", mark_problem_discussed)
    workflow.add_node("transition_stage", transition_stage)
    workflow.add_node("complete_interview", complete_interview)

    # 2. Add structural edges
    workflow.add_edge(START, "route_event")
    workflow.add_edge("record_question", END)
    workflow.add_edge("inject_guidance", END)
    workflow.add_edge("present_problem", END)
    workflow.add_edge("mark_problem_discussed", END)
    workflow.add_edge("transition_stage", END)
    workflow.add_edge("complete_interview", END)

    # 3. Default to in-memory checkpointer for thread isolation if not supplied
    if checkpointer is None:
        checkpointer = InMemorySaver()

    return workflow.compile(checkpointer=checkpointer)
