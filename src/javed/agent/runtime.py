"""Deep Agents & LangGraph agent runtime manager.

Provides orchestration, durable SQLite persistence, streaming events, real task planning,
and Zero-Trust security tool exclusion.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from deepagents import create_deep_agent
from langchain.agents.middleware.todo import TodoListMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
)
from langchain_openrouter import ChatOpenRouter
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from javed.agent.checkpointer import AgentCheckpointerManager
from javed.agent.security import (
    ALLOWED_TOOLS,
    EXCLUDED_TOOLS,
    ensure_agent_security_profile,
)
from javed.config import Settings, get_settings
from javed.schemas.agent import (
    AgentRuntimeStatusResponse,
    AgentStreamEvent,
    AgentStreamRequest,
    AgentThreadStateResponse,
    AgentTodoItem,
)
from javed.schemas.chat import ChatMessage, StreamUsage
from javed.services.openrouter import (
    AUTO_ROUTER_MODEL_ID,
    SUPPORTED_COST_TIERS,
    OpenRouterService,
)

logger = logging.getLogger("javed.agent.runtime")


class _StateReaderDummyModel(BaseChatModel):
    """Zero-call dummy model used strictly for reassembling checkpoint state graphs."""

    @property
    def _llm_type(self) -> str:
        return "state-reader-dummy"

    def _generate(self, messages: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("Dummy model must not be invoked during state inspection.")

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self


AGENT_SYSTEM_PROMPT: str = (
    "You are Javed, a stateful, observable AI agent powered by "
    "Deep Agents and LangGraph runtime.\n\n"
    "OPERATIONAL PRINCIPLES:\n"
    "1. TASK PLANNING: Whenever the user asks you to create an implementation plan, "
    "roadmap, multi-step workflow, or complex architectural task, you MUST call the "
    "`write_todos` tool to register each planned step as a todo item (with status "
    "'pending', 'in_progress', or 'completed') before or alongside providing your response. "
    "For simple, direct conversational questions, answer directly and concisely without "
    "creating task plans.\n"
    "2. ZERO-TRUST SECURITY & BOUNDARIES: You operate in BRICK-004 stateful planning and "
    "conversational mode. You DO NOT have access to arbitrary local files, host filesystem "
    "execution, command shells, or external actions. If the user asks to read, write, or "
    "delete files on their machine, or execute shell commands, explain clearly that host "
    "filesystem and execution tools are prohibited by your security boundary and not "
    "enabled in this brick.\n"
    "3. DURABLE STATE: Maintain thread context faithfully across turns."
)


class AgentRuntimeManager:
    """Manages Deep Agents execution lifecycle, SQLite checkpointing, and SSE event streaming."""

    def __init__(
        self,
        settings: Settings | None = None,
        openrouter_service: OpenRouterService | None = None,
        checkpointer_manager: AgentCheckpointerManager | None = None,
        model_override: BaseChatModel | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.openrouter_service = openrouter_service or OpenRouterService(self.settings)
        self.checkpointer_manager = checkpointer_manager or AgentCheckpointerManager(
            self.settings.agent_checkpoint_db_path
        )
        self.model_override = model_override
        self._is_initialized = False

    async def initialize(self) -> None:
        """Initialize the agent checkpointer and enforce Zero-Trust security profile."""
        if self._is_initialized:
            return

        ensure_agent_security_profile()
        await self.checkpointer_manager.initialize_async()
        self._is_initialized = True
        logger.info(
            "AgentRuntimeManager initialized (checkpoints: %s)",
            self.checkpointer_manager.db_path,
        )

    async def close(self) -> None:
        """Close checkpointer connections cleanly."""
        await self.checkpointer_manager.close()
        self._is_initialized = False
        logger.info("AgentRuntimeManager closed")

    def create_model(self, request: AgentStreamRequest) -> BaseChatModel:
        """Construct the LLM model instance for the agent run."""
        if self.model_override is not None:
            return self.model_override

        api_key = self.settings.openrouter_api_key
        if not api_key:
            raise ValueError(
                "OpenRouter API key is not configured. Set OPENROUTER_API_KEY in .env."
            )

        model_name = request.model or self.settings.openrouter_default_model
        plugins: list[dict[str, Any]] | None = None
        if model_name == AUTO_ROUTER_MODEL_ID:
            effective_cost_tier = (
                request.cost_tier or self.settings.openrouter_auto_router_cost_tier or "low"
            )
            if effective_cost_tier not in SUPPORTED_COST_TIERS:
                effective_cost_tier = "low"
            plugins = [{"id": "auto-router", "cost": effective_cost_tier}]

        session_id = request.session_id or request.thread_id

        return ChatOpenRouter(
            model_name=model_name,
            openrouter_api_key=api_key,
            openrouter_api_base=self.settings.openrouter_base_url,
            app_url=self.settings.app_url,
            app_title=self.settings.app_name,
            session_id=session_id,
            plugins=plugins,
            stream_usage=True,
            streaming=True,
            temperature=0.2,
        )

    def create_agent(
        self,
        model: BaseChatModel,
        checkpointer: BaseCheckpointSaver,
    ) -> CompiledStateGraph:
        """Construct the compiled Deep Agent state graph with TodoListMiddleware."""
        agent = create_deep_agent(
            model=model,
            system_prompt=AGENT_SYSTEM_PROMPT,
            middleware=[TodoListMiddleware()],
            checkpointer=checkpointer,
        )
        return agent

    async def stream_agent(self, request: AgentStreamRequest) -> AsyncIterator[AgentStreamEvent]:
        """Execute the agent run for a thread and stream typed agent lifecycle events."""
        if not self._is_initialized:
            await self.initialize()

        run_id = f"run_{uuid.uuid4().hex[:12]}"
        model_name = request.model or self.settings.openrouter_default_model
        effective_cost_tier = (
            request.cost_tier or self.settings.openrouter_auto_router_cost_tier or "low"
        )
        session_id = request.session_id or request.thread_id

        # 1. Emit run_started
        yield AgentStreamEvent(
            event="run_started",
            data={
                "run_id": run_id,
                "thread_id": request.thread_id,
                "model": model_name,
                "cost_tier": effective_cost_tier,
                "session_id": session_id,
            },
        )

        start_time = time.time()
        accumulated_chunks: list[str] = []
        token_index = 0
        todos: list[AgentTodoItem] = []
        upstream_reported_usage: dict[str, Any] | None = None
        selected_model: str | None = None

        try:
            model = self.create_model(request)
            checkpointer = await self.checkpointer_manager.get_async_checkpointer()
            agent = self.create_agent(model=model, checkpointer=checkpointer)

            config = {"configurable": {"thread_id": request.thread_id}}

            # Stream LangGraph events
            async for ev in agent.astream_events(
                {"messages": [HumanMessage(content=request.message)]},
                config=config,
                version="v2",
            ):
                event_type = ev.get("event")
                ev_name = ev.get("name")
                ev_data = ev.get("data", {})

                # Track write_todos tool start -> emit planning event
                if event_type == "on_tool_start" and ev_name == "write_todos":
                    input_args = ev_data.get("input", {})
                    raw_todos = input_args.get("todos", [])
                    if isinstance(raw_todos, list):
                        todos = [
                            AgentTodoItem(
                                id=f"todo_{idx + 1}",
                                content=item.get("content", ""),
                                status=item.get("status", "pending"),
                            )
                            for idx, item in enumerate(raw_todos)
                            if isinstance(item, dict)
                        ]
                        yield AgentStreamEvent(
                            event="planning",
                            data={
                                "run_id": run_id,
                                "thread_id": request.thread_id,
                                "todos": [t.model_dump() for t in todos],
                            },
                        )

                # Track write_todos tool end -> emit plan_updated event
                elif event_type == "on_tool_end" and ev_name == "write_todos":
                    output = ev_data.get("output")
                    if hasattr(output, "update") and isinstance(output.update, dict):
                        raw_todos = output.update.get("todos", [])
                        if isinstance(raw_todos, list):
                            todos = [
                                AgentTodoItem(
                                    id=f"todo_{idx + 1}",
                                    content=item.get("content", ""),
                                    status=item.get("status", "pending"),
                                )
                                for idx, item in enumerate(raw_todos)
                                if isinstance(item, dict)
                            ]
                    yield AgentStreamEvent(
                        event="plan_updated",
                        data={
                            "run_id": run_id,
                            "thread_id": request.thread_id,
                            "todos": [t.model_dump() for t in todos],
                        },
                    )

                # Stream model tokens
                elif event_type == "on_chat_model_stream":
                    chunk = ev_data.get("chunk")
                    if isinstance(chunk, AIMessageChunk) and chunk.content:
                        text = str(chunk.content)
                        accumulated_chunks.append(text)
                        yield AgentStreamEvent(
                            event="model_streaming",
                            data={
                                "run_id": run_id,
                                "thread_id": request.thread_id,
                                "delta": text,
                                "index": token_index,
                            },
                        )
                        token_index += 1

                # Track model completion metadata
                elif event_type == "on_chat_model_end":
                    output = ev_data.get("output")
                    if output and hasattr(output, "llm_output") and output.llm_output:
                        llm_out = output.llm_output
                        if "token_usage" in llm_out:
                            upstream_reported_usage = llm_out["token_usage"]
                        if "model_name" in llm_out:
                            selected_model = llm_out["model_name"]

            # 2. Extract final state from checkpointer
            final_state = await agent.aget_state(config)
            checkpoint_id = None
            if final_state and final_state.config:
                checkpoint_id = final_state.config.get("configurable", {}).get("checkpoint_id")
                if not todos and "todos" in final_state.values:
                    raw_todos = final_state.values.get("todos", [])
                    todos = [
                        AgentTodoItem(
                            id=f"todo_{idx + 1}",
                            content=item.get("content", ""),
                            status=item.get("status", "pending"),
                        )
                        for idx, item in enumerate(raw_todos)
                        if isinstance(item, dict)
                    ]

            # Emit checkpoint_saved
            yield AgentStreamEvent(
                event="checkpoint_saved",
                data={
                    "run_id": run_id,
                    "thread_id": request.thread_id,
                    "checkpoint_id": str(checkpoint_id) if checkpoint_id else None,
                },
            )

            # Reconcile final content
            final_content = "".join(accumulated_chunks)
            if not final_content and final_state and final_state.values.get("messages"):
                messages = final_state.values["messages"]
                for msg in reversed(messages):
                    if isinstance(msg, AIMessage) and msg.content:
                        final_content = str(msg.content)
                        break

            # Calculate usage and cost
            elapsed_ms = int((time.time() - start_time) * 1000)
            if upstream_reported_usage:
                prompt_tokens = int(upstream_reported_usage.get("prompt_tokens", 0))
                completion_tokens = int(upstream_reported_usage.get("completion_tokens", 0))
                total_tokens = int(
                    upstream_reported_usage.get("total_tokens", prompt_tokens + completion_tokens)
                )
                up_cost = upstream_reported_usage.get("cost")
                cost_usd = self.openrouter_service.calculate_cost(
                    model_id=model_name,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    upstream_cost=float(up_cost) if up_cost is not None else None,
                    selected_model=selected_model,
                )
                usage = StreamUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    cost_usd=cost_usd,
                    upstream_cost=float(up_cost) if up_cost is not None else None,
                    is_estimated=False,
                    cost_source="upstream" if up_cost is not None else "rate_card",
                    selected_model=selected_model or model_name,
                    requested_model=model_name,
                    cost_tier=effective_cost_tier,
                    session_id=session_id,
                )
            else:
                prompt_tokens = max(1, len(request.message) // 4)
                completion_tokens = max(1, len(final_content) // 4)
                cost_usd = self.openrouter_service.calculate_cost(
                    model_id=model_name,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    selected_model=selected_model,
                )
                usage = StreamUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                    cost_usd=cost_usd,
                    upstream_cost=None,
                    is_estimated=True,
                    cost_source="character_estimate",
                    selected_model=selected_model or model_name,
                    requested_model=model_name,
                    cost_tier=effective_cost_tier,
                    session_id=session_id,
                )

            # 3. Emit run_completed
            yield AgentStreamEvent(
                event="run_completed",
                data={
                    "run_id": run_id,
                    "thread_id": request.thread_id,
                    "content": final_content,
                    "todos": [t.model_dump() for t in todos],
                    "usage": usage.model_dump(),
                    "elapsed_ms": elapsed_ms,
                    "checkpoint_id": str(checkpoint_id) if checkpoint_id else None,
                },
            )

        except asyncio.CancelledError:
            logger.info("Agent run %s was cancelled by client", run_id)
            yield AgentStreamEvent(
                event="run_cancelled",
                data={
                    "run_id": run_id,
                    "thread_id": request.thread_id,
                    "reason": "client_cancelled",
                },
            )
            raise

        except Exception as e:
            logger.error("Agent run %s failed: %s", run_id, e, exc_info=True)
            yield AgentStreamEvent(
                event="run_failed",
                data={
                    "run_id": run_id,
                    "thread_id": request.thread_id,
                    "error": str(e),
                },
            )

    async def get_thread_state(self, thread_id: str) -> AgentThreadStateResponse:
        """Retrieve persisted messages and todo plan items for a specific thread."""
        if not self._is_initialized:
            await self.initialize()

        checkpointer = await self.checkpointer_manager.get_async_checkpointer()
        config = {"configurable": {"thread_id": thread_id}}
        tuple_ = await checkpointer.aget_tuple(config)

        if tuple_ is None or not tuple_.checkpoint:
            return AgentThreadStateResponse(
                thread_id=thread_id,
                messages=[],
                todos=[],
                checkpoint_id=None,
                exists=False,
            )

        reader_model = self.model_override or _StateReaderDummyModel()
        agent = self.create_agent(model=reader_model, checkpointer=checkpointer)
        state = await agent.aget_state(config)

        messages: list[ChatMessage] = []
        raw_messages = state.values.get("messages", []) if state else []
        for msg in raw_messages:
            if isinstance(msg, HumanMessage):
                messages.append(ChatMessage(role="user", content=str(msg.content)))
            elif isinstance(msg, AIMessage):
                # Only include assistant messages that have conversational content
                if msg.content:
                    messages.append(ChatMessage(role="assistant", content=str(msg.content)))
            elif isinstance(msg, SystemMessage):
                messages.append(ChatMessage(role="system", content=str(msg.content)))

        raw_todos = state.values.get("todos", []) if state else []
        todos = [
            AgentTodoItem(
                id=f"todo_{idx + 1}",
                content=item.get("content", ""),
                status=item.get("status", "pending"),
            )
            for idx, item in enumerate(raw_todos)
            if isinstance(item, dict)
        ]

        checkpoint_id = (
            state.config.get("configurable", {}).get("checkpoint_id")
            if state and state.config
            else tuple_.checkpoint.get("id")
        )

        return AgentThreadStateResponse(
            thread_id=thread_id,
            messages=messages,
            todos=todos,
            checkpoint_id=str(checkpoint_id) if checkpoint_id else None,
            exists=True,
        )

    async def get_status(self) -> AgentRuntimeStatusResponse:
        """Query agent runtime status, checkpointer state, and tool boundaries."""
        if not self._is_initialized:
            await self.initialize()

        return AgentRuntimeStatusResponse(
            status="ready",
            checkpointer="sqlite",
            checkpoint_db_path=self.checkpointer_manager.db_path,
            security_profile="zero-trust-planning-only",
            allowed_tools=list(ALLOWED_TOOLS),
            excluded_tools=sorted(list(EXCLUDED_TOOLS)),
        )
