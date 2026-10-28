"""Deep Agents & LangGraph agent runtime manager.

Provides orchestration, durable SQLite persistence, streaming events, real task planning,
positive tool allowlist enforcement, and per-thread concurrency serialization.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Literal

from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from langchain.agents.middleware.todo import TodoListMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_openrouter import ChatOpenRouter
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from javed.agent.checkpointer import AgentCheckpointerManager
from javed.agent.security import (
    ALLOWED_TOOLS,
    EXCLUDED_TOOLS,
    PositiveToolAllowlistMiddleware,
    assert_safe_agent_runtime,
    ensure_agent_security_profile,
)
from javed.config import Settings, get_settings
from javed.mcp.approval_store import ApprovalStore, redact_sensitive_value
from javed.mcp.gateway import SecureMCPGateway, current_approval_context
from javed.schemas.agent import (
    AgentRuntimeStatusResponse,
    AgentStreamEvent,
    AgentStreamRequest,
    AgentThreadStateResponse,
    AgentTodoItem,
    ToolActivityRecord,
    ToolLifecycleState,
    extract_message_text,
    validate_thread_id,
)
from javed.schemas.approval import ApprovalRecord, compute_argument_digest
from javed.schemas.chat import ChatMessage, StreamUsage
from javed.schemas.mcp import parse_namespaced_tool_id
from javed.services.openrouter import (
    AUTO_ROUTER_MODEL_ID,
    SUPPORTED_COST_TIERS,
    OpenRouterService,
)

logger = logging.getLogger("javed.agent.runtime")


class ThreadLockManager:
    """Serializes execution within the same thread to prevent concurrent checkpoint corruption.

    Maintains per-thread asyncio.Lock instances so multiple requests targeting different
    threads execute in parallel, while concurrent runs on the exact same thread ID are
    safely serialized in FIFO order.
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._registry_lock = asyncio.Lock()

    async def get_lock(self, thread_id: str) -> asyncio.Lock:
        """Get or create an asyncio.Lock for the specified thread_id."""
        async with self._registry_lock:
            if thread_id not in self._locks:
                self._locks[thread_id] = asyncio.Lock()
            return self._locks[thread_id]

    @asynccontextmanager
    async def lock_thread(self, thread_id: str) -> AsyncIterator[None]:
        """Context manager to acquire and release the lock for a specific thread."""
        lock = await self.get_lock(thread_id)
        async with lock:
            yield


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


class DeterministicScriptedE2EModel(BaseChatModel):
    """Deterministic scripted model used strictly for automated E2E browser verification."""

    @property
    def _llm_type(self) -> str:
        return "deterministic-scripted-e2e-model"

    def _generate(
        self,
        messages: Any,
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        tool_messages = [
            m
            for m in messages
            if getattr(m, "type", None) == "tool" or type(m).__name__ == "ToolMessage"
        ]
        if tool_messages:
            last_tool_msg = tool_messages[-1]
            content_str = str(last_tool_msg.content)
            status_str = getattr(last_tool_msg, "status", "")
            if "cancelled" in content_str.lower() or "rejected" in content_str.lower():
                resp_text = (
                    "The time request was rejected by human operator. Execution safely cancelled."
                )
            elif (
                status_str == "error"
                or "error" in content_str.lower()
                or "failed" in content_str.lower()
                or "violation" in content_str.lower()
            ):
                resp_text = f"Tool execution failed: {content_str}."
            else:
                resp_text = f"The time operation was authorized and executed: {content_str}."
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=resp_text))])

        call_id = f"call_e2e_{uuid.uuid4().hex[:8]}"
        last_human_text = ""
        for m in reversed(messages):
            if getattr(m, "type", None) == "human" or type(m).__name__ == "HumanMessage":
                last_human_text = str(getattr(m, "content", ""))
                break

        tz = (
            "Invalid/Nonexistent_Timezone"
            if "invalid" in last_human_text.lower() or "fail" in last_human_text.lower()
            else "UTC"
        )
        tool_call = {
            "name": "time__get_current_time",
            "args": {"timezone": tz},
            "id": call_id,
            "type": "tool_call",
        }
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[tool_call]))]
        )

    async def _agenerate(
        self,
        messages: Any,
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)

    async def _astream(
        self,
        messages: Any,
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        res = self._generate(messages, stop, run_manager, **kwargs)
        msg = res.generations[0].message
        if msg.tool_calls:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {
                            "name": tc["name"],
                            "args": json.dumps(tc["args"]),
                            "id": tc["id"],
                            "index": 0,
                        }
                        for tc in msg.tool_calls
                    ],
                )
            )
        else:
            text = str(msg.content)
            words = text.split(" ")
            for i in range(0, len(words), 3):
                chunk = " ".join(words[i : i + 3]) + " "
                yield ChatGenerationChunk(message=AIMessageChunk(content=chunk))

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self


class AgentRuntimeManager:
    """Manages Deep Agents execution lifecycle, SQLite checkpointing, and SSE event streaming."""

    def __init__(
        self,
        settings: Settings | None = None,
        openrouter_service: OpenRouterService | None = None,
        checkpointer_manager: AgentCheckpointerManager | None = None,
        model_override: BaseChatModel | None = None,
        mcp_gateway: SecureMCPGateway | None = None,
        approval_store: ApprovalStore | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.openrouter_service = openrouter_service or OpenRouterService(self.settings)
        self.checkpointer_manager = checkpointer_manager or AgentCheckpointerManager(
            self.settings.agent_checkpoint_db_path
        )
        self.model_override = model_override
        self.approval_store = approval_store or ApprovalStore(self.settings.agent_approvals_db_path)
        if mcp_gateway is not None and mcp_gateway.approval_store is None:
            mcp_gateway.approval_store = self.approval_store
        self.mcp_gateway = mcp_gateway
        self.thread_lock_manager = ThreadLockManager()
        self._is_initialized = False

    async def initialize(self) -> None:
        """Initialize checkpointer, approval store, and enforce Zero-Trust security profile."""
        if self._is_initialized:
            return

        try:
            ensure_agent_security_profile()
            await self.checkpointer_manager.initialize_async()
            await self.approval_store.initialize()
            if self.mcp_gateway is not None and self.mcp_gateway.approval_store is None:
                self.mcp_gateway.approval_store = self.approval_store
            self._is_initialized = True
            logger.info(
                "AgentRuntimeManager initialized (checkpoints: %s, approvals: %s)",
                self.checkpointer_manager.db_path,
                self.approval_store.db_path,
            )
        except Exception:
            await self.close()
            raise

    async def close(self) -> None:
        """Close checkpointer, approval store, and active MCP transports cleanly."""
        if self.mcp_gateway is not None and getattr(self.mcp_gateway, "registry", None) is not None:
            try:
                await self.mcp_gateway.registry.disconnect_all()
            except Exception as e:
                logger.warning("Error disconnecting MCP servers on runtime close: %s", e)
        if hasattr(self.checkpointer_manager, "close"):
            try:
                await self.checkpointer_manager.close()
            except Exception as e:
                logger.warning("Error closing checkpointer manager on runtime close: %s", e)
        if hasattr(self.approval_store, "close"):
            try:
                await self.approval_store.close()
            except Exception as e:
                logger.warning("Error closing approval store on runtime close: %s", e)
        self._is_initialized = False
        logger.info("AgentRuntimeManager closed")

    def create_model(self, request: AgentStreamRequest) -> BaseChatModel:
        """Construct the LLM model instance for the agent run."""
        if self.model_override is not None:
            return self.model_override

        if os.getenv("JAVED_E2E_TEST_MODE", "").strip().lower() in ("1", "true", "yes"):
            return DeterministicScriptedE2EModel()

        api_key = self.settings.openrouter_api_key
        if not api_key:
            raise ValueError(
                "OpenRouter API key is not configured. Set OPENROUTER_API_KEY in .env."
            )

        model_name = request.model or self.settings.openrouter_default_model
        fallback_reason: str | None = None

        # Check tool compatibility if tools are executable or visible
        has_executable_tools = bool(self.mcp_gateway and self.mcp_gateway.get_executable_tools())
        if has_executable_tools and model_name != AUTO_ROUTER_MODEL_ID:
            if not self.openrouter_service.supports_tools(model_name):
                cheapest = self.openrouter_service.get_best_tool_capable_model()
                logger.warning(
                    "Requested model '%s' lacks structured tool calling support. "
                    "Safely falling back to verified tool-capable model '%s'.",
                    model_name,
                    cheapest,
                )
                fallback_reason = (
                    f"Requested model '{model_name}' does not support tool calling. "
                    f"Safely fell back to '{cheapest}'."
                )
                model_name = cheapest

        requested_plugins = list(request.plugins) if request.plugins else []
        plugins: list[dict[str, Any]] | None = None
        if model_name == AUTO_ROUTER_MODEL_ID:
            effective_cost_tier = (
                request.cost_tier or self.settings.openrouter_auto_router_cost_tier or "low"
            )
            if effective_cost_tier not in SUPPORTED_COST_TIERS:
                effective_cost_tier = "low"
            plugins = [{"id": "auto-router", "cost": effective_cost_tier}]
        elif requested_plugins:
            plugins = requested_plugins

        # Section 7 security guard: ensure NO provider-hosted server tools permitted
        all_plugins_to_check = (plugins or []) + requested_plugins
        for p in all_plugins_to_check:
            p_id = str(p.get("id", "")).lower()
            if p_id != "auto-router":
                raise PermissionError(
                    f"Security Violation: OpenRouter plugin '{p_id}' prohibited in BRICK-005. "
                    "Only user-defined local MCP gateway tools are authorized."
                )

        session_id = request.session_id or request.thread_id

        chat_model = ChatOpenRouter(
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
        chat_model._effective_model_name = model_name
        chat_model._fallback_reason = fallback_reason
        return chat_model

    def create_agent(
        self,
        model: BaseChatModel,
        checkpointer: BaseCheckpointSaver,
    ) -> CompiledStateGraph:
        """Construct compiled Deep Agent state graph with safe backend,
        positive allowlist, and HITL.
        """
        mcp_tools = self.mcp_gateway.build_langchain_tools() if self.mcp_gateway else []
        middleware = [
            TodoListMiddleware(),
            PositiveToolAllowlistMiddleware(gateway=self.mcp_gateway),
        ]

        approval_tools = self.mcp_gateway.get_approval_required_tools() if self.mcp_gateway else []
        interrupt_on = (
            {tid: {"allowed_decisions": ["approve", "reject"]} for tid in approval_tools}
            if approval_tools
            else None
        )

        agent = create_deep_agent(
            model=model,
            tools=mcp_tools,
            system_prompt=AGENT_SYSTEM_PROMPT,
            middleware=middleware,
            backend=StateBackend(),
            checkpointer=checkpointer,
            interrupt_on=interrupt_on,
        )
        assert_safe_agent_runtime(agent, gateway=self.mcp_gateway)
        return agent

    async def stream_agent(self, request: AgentStreamRequest) -> AsyncIterator[AgentStreamEvent]:
        """Execute the agent run for a thread and stream typed agent lifecycle events."""
        # 1. Validate thread_id to prevent path traversal or injection
        validated_thread_id = validate_thread_id(request.thread_id)

        if not self._is_initialized:
            await self.initialize()

        run_id = f"run_{uuid.uuid4().hex[:12]}"
        model_name = request.model or self.settings.openrouter_default_model
        effective_cost_tier = (
            request.cost_tier or self.settings.openrouter_auto_router_cost_tier or "low"
        )
        session_id = request.session_id or validated_thread_id

        # 2. Serialize runs on the same thread ID using ThreadLockManager
        async with self.thread_lock_manager.lock_thread(validated_thread_id):
            # Emit run_started
            yield AgentStreamEvent(
                event="run_started",
                data={
                    "run_id": run_id,
                    "thread_id": validated_thread_id,
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
            total_prompt_tokens = 0
            total_completion_tokens = 0
            total_upstream_cost = 0.0
            has_upstream_usage = False
            pending_tool_call_ids: dict[str, list[str]] = defaultdict(list)
            run_to_tool_call_id: dict[str, str] = {}

            try:
                model = self.create_model(request)
                checkpointer = await self.checkpointer_manager.get_async_checkpointer()
                agent = self.create_agent(model=model, checkpointer=checkpointer)

                config = {"configurable": {"thread_id": validated_thread_id}}

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
                                    "thread_id": validated_thread_id,
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
                                "thread_id": validated_thread_id,
                                "todos": [t.model_dump() for t in todos],
                            },
                        )

                    # Track external / MCP tool starts
                    elif event_type == "on_tool_start":
                        if ev_name != "write_todos":
                            server_id = "unknown"
                            tool_desc = ""
                            if self.mcp_gateway:
                                try:
                                    server_id, _ = parse_namespaced_tool_id(ev_name)
                                except Exception:
                                    server_id = "unknown"
                                t_rec = self.mcp_gateway.registry.get_tool(ev_name)
                                if t_rec:
                                    tool_desc = t_rec.description

                            tc_id = ev.get("metadata", {}).get("tool_call_id")
                            if not tc_id and pending_tool_call_ids.get(ev_name):
                                tc_id = pending_tool_call_ids[ev_name].pop(0)
                            if not tc_id:
                                tc_id = ev.get("run_id")

                            if ev.get("run_id") and tc_id:
                                run_to_tool_call_id[ev["run_id"]] = tc_id

                            yield AgentStreamEvent(
                                event="tool_started",
                                data={
                                    "run_id": run_id,
                                    "thread_id": validated_thread_id,
                                    "tool": ev_name,
                                    "server_id": server_id,
                                    "description": tool_desc,
                                    "input": redact_sensitive_value(ev_data.get("input", {})),
                                    "tool_call_id": tc_id,
                                },
                            )

                    # Track external / MCP tool completions
                    elif event_type == "on_tool_end":
                        if ev_name != "write_todos":
                            output_val = ev_data.get("output", "")
                            server_id = "unknown"
                            if self.mcp_gateway:
                                try:
                                    server_id, _ = parse_namespaced_tool_id(ev_name)
                                except Exception:
                                    server_id = "unknown"

                            is_error = False
                            err_msg = ""
                            if isinstance(output_val, ToolMessage) and output_val.status == "error":
                                is_error = True
                                err_msg = str(output_val.content)
                            elif hasattr(output_val, "status") and output_val.status == "error":
                                is_error = True
                                err_msg = str(getattr(output_val, "content", output_val))
                            elif (
                                "Security Violation:" in str(output_val)
                                or "Error executing tool" in str(output_val)
                                or "MCP server returned tool error" in str(output_val)
                            ):
                                is_error = True
                                err_msg = str(output_val)

                            tc_id = getattr(output_val, "tool_call_id", None)
                            ev_r_id = ev.get("run_id")
                            if not tc_id and ev_r_id and ev_r_id in run_to_tool_call_id:
                                tc_id = run_to_tool_call_id[ev_r_id]
                            if not tc_id:
                                tc_id = ev.get("metadata", {}).get("tool_call_id")
                            if not tc_id and pending_tool_call_ids.get(ev_name):
                                tc_id = pending_tool_call_ids[ev_name].pop(0)
                            if not tc_id:
                                tc_id = ev.get("run_id")

                            if is_error:
                                yield AgentStreamEvent(
                                    event="tool_failed",
                                    data={
                                        "run_id": run_id,
                                        "thread_id": validated_thread_id,
                                        "tool": ev_name,
                                        "server_id": server_id,
                                        "error": err_msg[:1000],
                                        "tool_call_id": tc_id,
                                    },
                                )
                            else:
                                out_str = str(getattr(output_val, "content", output_val))[:1000]
                                yield AgentStreamEvent(
                                    event="tool_completed",
                                    data={
                                        "run_id": run_id,
                                        "thread_id": validated_thread_id,
                                        "tool": ev_name,
                                        "server_id": server_id,
                                        "output": out_str,
                                        "tool_call_id": tc_id,
                                    },
                                )

                    elif event_type == "on_tool_error":
                        if ev_name != "write_todos":
                            err_val = ev_data.get("error", "Tool execution error")
                            server_id = "unknown"
                            if self.mcp_gateway:
                                try:
                                    server_id, _ = parse_namespaced_tool_id(ev_name)
                                except Exception:
                                    server_id = "unknown"

                            tc_id = None
                            if ev.get("run_id") and ev["run_id"] in run_to_tool_call_id:
                                tc_id = run_to_tool_call_id[ev["run_id"]]
                            if not tc_id:
                                tc_id = ev.get("metadata", {}).get("tool_call_id")
                            if not tc_id and pending_tool_call_ids.get(ev_name):
                                tc_id = pending_tool_call_ids[ev_name].pop(0)
                            if not tc_id:
                                tc_id = ev.get("run_id")

                            yield AgentStreamEvent(
                                event="tool_failed",
                                data={
                                    "run_id": run_id,
                                    "thread_id": validated_thread_id,
                                    "tool": ev_name,
                                    "server_id": server_id,
                                    "error": str(err_val)[:1000],
                                    "tool_call_id": tc_id,
                                },
                            )

                    # Stream model tokens
                    elif event_type == "on_chat_model_stream":
                        chunk = ev_data.get("chunk")
                        if isinstance(chunk, AIMessageChunk) and chunk.content:
                            text = extract_message_text(chunk.content)
                            if text:
                                accumulated_chunks.append(text)
                                yield AgentStreamEvent(
                                    event="model_streaming",
                                    data={
                                        "run_id": run_id,
                                        "thread_id": validated_thread_id,
                                        "delta": text,
                                        "index": token_index,
                                    },
                                )
                                token_index += 1

                    # Track model completion metadata & tool requests
                    elif event_type == "on_chat_model_end":
                        output = ev_data.get("output")
                        # 1. Check llm_output
                        if output and hasattr(output, "llm_output") and output.llm_output:
                            llm_out = output.llm_output
                            if "token_usage" in llm_out and isinstance(
                                llm_out["token_usage"], dict
                            ):
                                upstream_reported_usage = llm_out["token_usage"]
                                p = int(upstream_reported_usage.get("prompt_tokens", 0))
                                c = int(upstream_reported_usage.get("completion_tokens", 0))
                                if p or c:
                                    total_prompt_tokens += p
                                    total_completion_tokens += c
                                    has_upstream_usage = True
                                cost_val = upstream_reported_usage.get("cost")
                                if cost_val is not None:
                                    try:
                                        total_upstream_cost += float(cost_val)
                                    except (ValueError, TypeError):
                                        pass
                            if "model_name" in llm_out and not selected_model:
                                selected_model = str(llm_out["model_name"])

                        # 2. Extract from AIMessage (usage_metadata and response_metadata)
                        msg_obj = output if isinstance(output, AIMessage) else None
                        if not msg_obj and hasattr(output, "generations") and output.generations:
                            for gen_list in output.generations:
                                items = gen_list if isinstance(gen_list, list) else [gen_list]
                                for g in items:
                                    if hasattr(g, "message") and isinstance(g.message, AIMessage):
                                        msg_obj = g.message
                                        break
                                if msg_obj:
                                    break

                        if msg_obj:
                            if hasattr(msg_obj, "usage_metadata") and msg_obj.usage_metadata:
                                um = msg_obj.usage_metadata
                                p = int(um.get("input_tokens", 0))
                                c = int(um.get("output_tokens", 0))
                                if p or c:
                                    total_prompt_tokens += p
                                    total_completion_tokens += c
                                    has_upstream_usage = True
                            if hasattr(msg_obj, "response_metadata") and msg_obj.response_metadata:
                                rm = msg_obj.response_metadata
                                if "model_name" in rm and not selected_model:
                                    selected_model = str(rm["model_name"])
                                cost_val = rm.get("cost")
                                if (
                                    cost_val is None
                                    and "cost_details" in rm
                                    and isinstance(rm["cost_details"], dict)
                                ):
                                    cost_val = rm["cost_details"].get("upstream_inference_cost")
                                if cost_val is not None:
                                    try:
                                        total_upstream_cost += float(cost_val)
                                    except (ValueError, TypeError):
                                        pass

                        # Check if model requested tool calls
                        requested_calls: list[dict[str, Any]] = []
                        if hasattr(output, "generations") and output.generations:
                            for gen_list in output.generations:
                                items = gen_list if isinstance(gen_list, list) else [gen_list]
                                for g in items:
                                    msg = getattr(g, "message", None)
                                    if msg and getattr(msg, "tool_calls", None):
                                        requested_calls.extend(msg.tool_calls)
                        elif isinstance(output, AIMessage) and output.tool_calls:
                            requested_calls.extend(output.tool_calls)

                        for tc in requested_calls:
                            tc_name = tc.get("name", "")
                            tc_id = tc.get("id")
                            if tc_name and tc_id:
                                pending_tool_call_ids[tc_name].append(tc_id)
                            if tc_name and tc_name != "write_todos":
                                server_id = "unknown"
                                tool_desc = ""
                                if self.mcp_gateway:
                                    try:
                                        server_id, _ = parse_namespaced_tool_id(tc_name)
                                    except Exception:
                                        server_id = "unknown"
                                    t_rec = self.mcp_gateway.registry.get_tool(tc_name)
                                    if t_rec:
                                        tool_desc = t_rec.description
                                yield AgentStreamEvent(
                                    event="tool_requested",
                                    data={
                                        "run_id": run_id,
                                        "thread_id": validated_thread_id,
                                        "tool": tc_name,
                                        "server_id": server_id,
                                        "description": tool_desc,
                                        "tool_call_id": tc.get("id"),
                                        "input": redact_sensitive_value(tc.get("args") or {}),
                                    },
                                )

                # Extract final state from checkpointer
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

                # Check if execution paused on a Human-in-the-Loop interrupt
                interrupted_approvals: list[ApprovalRecord] = []
                if final_state and final_state.tasks:
                    for task in final_state.tasks:
                        if task.interrupts:
                            for intr in task.interrupts:
                                intr_val = intr.value
                                intr_id = getattr(intr, "id", str(uuid.uuid4()))
                                action_requests = (
                                    intr_val.get("action_requests", [])
                                    if isinstance(intr_val, dict)
                                    else []
                                )
                                for act in action_requests:
                                    tool_name = act.get("name", "")
                                    tool_args = act.get("args", {})
                                    tool_call_id = f"call_{uuid.uuid4().hex[:8]}"
                                    if final_state.values.get("messages"):
                                        for m in reversed(final_state.values["messages"]):
                                            if isinstance(m, AIMessage) and m.tool_calls:
                                                for tc in m.tool_calls:
                                                    if tc.get("name") == tool_name:
                                                        tool_call_id = tc.get("id") or tool_call_id
                                                        break
                                                break

                                    server_id = "unknown"
                                    tool_fingerprint = ""
                                    policy_ver = 0
                                    if self.mcp_gateway:
                                        try:
                                            server_id, _ = parse_namespaced_tool_id(tool_name)
                                        except Exception:
                                            server_id = "unknown"
                                        t_rec = self.mcp_gateway.registry.get_tool(tool_name)
                                        if t_rec:
                                            tool_fingerprint = t_rec.fingerprint
                                        policy_ver = self.mcp_gateway.policy_version

                                    arg_digest = compute_argument_digest(tool_args)
                                    approval_id = f"appr_{uuid.uuid4().hex[:12]}"
                                    rec = ApprovalRecord(
                                        approval_id=approval_id,
                                        interrupt_id=intr_id,
                                        run_id=run_id,
                                        thread_id=validated_thread_id,
                                        server_id=server_id,
                                        tool_id=tool_name,
                                        tool_call_id=tool_call_id,
                                        arguments=tool_args,
                                        argument_digest=arg_digest,
                                        tool_fingerprint=tool_fingerprint,
                                        policy_version=policy_ver,
                                        created_at=datetime.now(UTC),
                                        status="pending",
                                        dispatch_status="not_dispatched",
                                    )
                                    saved_rec = await self.approval_store.create_approval(rec)
                                    interrupted_approvals.append(saved_rec)

                # Emit checkpoint_saved
                yield AgentStreamEvent(
                    event="checkpoint_saved",
                    data={
                        "run_id": run_id,
                        "thread_id": validated_thread_id,
                        "checkpoint_id": str(checkpoint_id) if checkpoint_id else None,
                    },
                )

                # If paused for approval, emit approval_required and release the lock
                # without emitting run_completed
                if interrupted_approvals:
                    logger.info(
                        "Agent execution paused for human approval on thread %s (%d pending calls)",
                        validated_thread_id,
                        len(interrupted_approvals),
                    )
                    for appr in interrupted_approvals:
                        yield AgentStreamEvent(
                            event="approval_required",
                            data={
                                "approval_id": appr.approval_id,
                                "interrupt_id": appr.interrupt_id,
                                "run_id": run_id,
                                "thread_id": validated_thread_id,
                                "server_id": appr.server_id,
                                "tool_id": appr.tool_id,
                                "tool_call_id": appr.tool_call_id,
                                "arguments": redact_sensitive_value(appr.arguments),
                                "argument_digest": appr.argument_digest,
                                "tool_fingerprint": appr.tool_fingerprint,
                                "policy_version": appr.policy_version,
                                "status": "pending",
                                "created_at": appr.created_at.isoformat(),
                            },
                        )
                    return

                # Reconcile final content
                final_content = "".join(accumulated_chunks)
                if not final_content and final_state and final_state.values.get("messages"):
                    messages = final_state.values["messages"]
                    for msg in reversed(messages):
                        if isinstance(msg, AIMessage):
                            text = extract_message_text(msg.content)
                            if text:
                                final_content = text
                                break

                # Calculate usage and cost
                elapsed_ms = int((time.time() - start_time) * 1000)
                effective_model = (
                    selected_model or getattr(model, "_effective_model_name", None) or model_name
                )
                if has_upstream_usage:
                    prompt_tokens = total_prompt_tokens
                    completion_tokens = total_completion_tokens
                    total_tokens = prompt_tokens + completion_tokens
                    up_cost = total_upstream_cost if total_upstream_cost > 0.0 else None
                    cost_usd = self.openrouter_service.calculate_cost(
                        model_id=effective_model,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        upstream_cost=up_cost,
                        selected_model=effective_model,
                    )
                    usage = StreamUsage(
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                        cost_usd=cost_usd,
                        upstream_cost=up_cost,
                        is_estimated=False,
                        cost_source="upstream" if up_cost is not None else "rate_card",
                        selected_model=effective_model,
                        requested_model=model_name,
                        cost_tier=effective_cost_tier,
                        session_id=session_id,
                    )
                else:
                    prompt_tokens = max(1, len(request.message) // 4)
                    completion_tokens = max(1, len(final_content) // 4)
                    cost_usd = self.openrouter_service.calculate_cost(
                        model_id=effective_model,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        selected_model=effective_model,
                    )
                    usage = StreamUsage(
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=prompt_tokens + completion_tokens,
                        cost_usd=cost_usd,
                        upstream_cost=None,
                        is_estimated=True,
                        cost_source="character_estimate",
                        selected_model=effective_model,
                        requested_model=model_name,
                        cost_tier=effective_cost_tier,
                        session_id=session_id,
                    )

                # Emit run_completed
                yield AgentStreamEvent(
                    event="run_completed",
                    data={
                        "run_id": run_id,
                        "thread_id": validated_thread_id,
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
                        "thread_id": validated_thread_id,
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
                        "thread_id": validated_thread_id,
                        "error": str(e),
                    },
                )

    async def resume_agent(
        self,
        thread_id: str,
        approval_id: str,
        decision: Literal["approve", "reject"],
        reason: str | None = None,
        model_name_override: str | None = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        """Resume an interrupted agent run following human approval or rejection.

        Canonical API method. Requires explicit, unambiguously ordered parameters:
        thread_id, approval_id, decision ('approve' | 'reject').
        """
        if str(decision).lower() not in ("approve", "reject"):
            raise ValueError(
                f"Invalid decision '{decision}'. Decision must be strictly 'approve' or 'reject'."
            )
        if str(thread_id).lower() in ("approve", "reject"):
            raise ValueError(
                f"Invalid thread_id '{thread_id}': cannot be 'approve' or 'reject'. "
                "Positional parameters appear swapped: expected (thread_id, approval_id, decision)."
            )
        if str(approval_id).lower() in ("approve", "reject"):
            raise ValueError(
                f"Invalid approval_id '{approval_id}': cannot be 'approve' or 'reject'. "
                "Positional parameters appear swapped: expected (thread_id, approval_id, decision)."
            )
        validated_thread_id = validate_thread_id(thread_id)

        if not self._is_initialized:
            await self.initialize()

        run_id = f"run_resume_{uuid.uuid4().hex[:8]}"

        async with self.thread_lock_manager.lock_thread(validated_thread_id):
            approval = await self.approval_store.get_approval(approval_id)
            if not approval:
                # Check if caller swapped approval_id and thread_id
                swapped = await self.approval_store.get_approval(validated_thread_id)
                if swapped is not None:
                    raise ValueError(
                        f"Positional parameters appear swapped: '{validated_thread_id}' is an "
                        "approval ID, not a thread ID. "
                        "Expected (thread_id, approval_id, decision)."
                    )
                raise KeyError(f"Approval '{approval_id}' not found.")
            if approval.thread_id != validated_thread_id:
                raise ValueError(
                    f"Thread mismatch: Approval '{approval_id}' belongs to thread "
                    f"'{approval.thread_id}', not '{validated_thread_id}'."
                )
            if approval.status != "pending":
                raise ValueError(
                    f"Approval '{approval_id}' cannot be decided; "
                    f"current status is '{approval.status}'."
                )

            # Atomically record decision in durable store
            updated_approval = await self.approval_store.record_decision(
                approval_id=approval_id,
                decision=decision,
                expected_thread_id=validated_thread_id,
                decider="human_user",
                reason=reason,
            )

            # Emit decision lifecycle event
            if decision == "approve":
                yield AgentStreamEvent(
                    event="approval_approved",
                    data={
                        "approval_id": approval_id,
                        "thread_id": validated_thread_id,
                        "run_id": run_id,
                    },
                )
            else:
                yield AgentStreamEvent(
                    event="approval_rejected",
                    data={
                        "approval_id": approval_id,
                        "thread_id": validated_thread_id,
                        "run_id": run_id,
                        "reason": reason,
                    },
                )

            # Emit agent_resumed lifecycle event
            yield AgentStreamEvent(
                event="agent_resumed",
                data={
                    "approval_id": approval_id,
                    "thread_id": validated_thread_id,
                    "run_id": run_id,
                    "decision": decision,
                },
            )

            start_time = time.time()
            accumulated_chunks: list[str] = []
            token_index = 0
            todos: list[AgentTodoItem] = []
            upstream_reported_usage: dict[str, Any] | None = None
            selected_model: str | None = None
            total_prompt_tokens = 0
            total_completion_tokens = 0
            total_upstream_cost = 0.0
            has_upstream_usage = False
            model_name = model_name_override or self.settings.openrouter_default_model
            effective_cost_tier = self.settings.openrouter_auto_router_cost_tier or "low"

            dec_item: dict[str, Any] = {"type": decision}
            if reason and decision == "reject":
                dec_item["message"] = reason
            command = Command(resume={"decisions": [dec_item]})

            try:
                # Bind validated approval record to current execution context
                token = current_approval_context.set(updated_approval)
                try:
                    checkpointer = await self.checkpointer_manager.get_async_checkpointer()
                    model_req = AgentStreamRequest(
                        thread_id=validated_thread_id,
                        message="[resumed approval invocation]",
                        model=model_name_override,
                    )
                    model = self.create_model(model_req)
                    agent = self.create_agent(model=model, checkpointer=checkpointer)
                    config = {"configurable": {"thread_id": validated_thread_id}}

                    async for ev in agent.astream_events(command, config=config, version="v2"):
                        event_type = ev.get("event")
                        ev_name = ev.get("name")
                        ev_data = ev.get("data", {})

                        if event_type == "on_tool_start":
                            if ev_name != "write_todos":
                                server_id = "unknown"
                                tool_desc = ""
                                if self.mcp_gateway:
                                    try:
                                        server_id, _ = parse_namespaced_tool_id(ev_name)
                                    except Exception:
                                        server_id = "unknown"
                                    t_rec = self.mcp_gateway.registry.get_tool(ev_name)
                                    if t_rec:
                                        tool_desc = t_rec.description

                                tc_id = (
                                    ev.get("metadata", {}).get("tool_call_id")
                                    or approval.tool_call_id
                                    or ev.get("run_id")
                                )

                                yield AgentStreamEvent(
                                    event="tool_started",
                                    data={
                                        "run_id": run_id,
                                        "thread_id": validated_thread_id,
                                        "tool": ev_name,
                                        "server_id": server_id,
                                        "description": tool_desc,
                                        "input": redact_sensitive_value(ev_data.get("input", {})),
                                        "tool_call_id": tc_id,
                                    },
                                )

                        elif event_type == "on_tool_end":
                            if ev_name != "write_todos":
                                output_val = ev_data.get("output", "")
                                server_id = "unknown"
                                if self.mcp_gateway:
                                    try:
                                        server_id, _ = parse_namespaced_tool_id(ev_name)
                                    except Exception:
                                        server_id = "unknown"

                                is_error = False
                                err_msg = ""
                                if (
                                    isinstance(output_val, ToolMessage)
                                    and output_val.status == "error"
                                ):
                                    is_error = True
                                    err_msg = str(output_val.content)
                                elif hasattr(output_val, "status") and output_val.status == "error":
                                    is_error = True
                                    err_msg = str(getattr(output_val, "content", output_val))
                                elif (
                                    "Security Violation:" in str(output_val)
                                    or "Error executing tool" in str(output_val)
                                    or "MCP server returned tool error" in str(output_val)
                                ):
                                    is_error = True
                                    err_msg = str(output_val)

                                tool_call_id = (
                                    getattr(output_val, "tool_call_id", None)
                                    or ev.get("metadata", {}).get("tool_call_id")
                                    or approval.tool_call_id
                                    or ev.get("run_id")
                                )

                                if is_error:
                                    yield AgentStreamEvent(
                                        event="tool_failed",
                                        data={
                                            "run_id": run_id,
                                            "thread_id": validated_thread_id,
                                            "tool": ev_name,
                                            "server_id": server_id,
                                            "error": err_msg[:1000],
                                            "tool_call_id": tool_call_id,
                                        },
                                    )
                                else:
                                    out_str = str(getattr(output_val, "content", output_val))[:1000]
                                    yield AgentStreamEvent(
                                        event="tool_completed",
                                        data={
                                            "run_id": run_id,
                                            "thread_id": validated_thread_id,
                                            "tool": ev_name,
                                            "server_id": server_id,
                                            "output": out_str,
                                            "tool_call_id": tool_call_id,
                                        },
                                    )

                        elif event_type == "on_tool_error":
                            if ev_name != "write_todos":
                                err_val = ev_data.get("error", "Tool execution error")
                                server_id = "unknown"
                                if self.mcp_gateway:
                                    try:
                                        server_id, _ = parse_namespaced_tool_id(ev_name)
                                    except Exception:
                                        server_id = "unknown"

                                tc_id = (
                                    ev.get("metadata", {}).get("tool_call_id")
                                    or approval.tool_call_id
                                    or ev.get("run_id")
                                )

                                yield AgentStreamEvent(
                                    event="tool_failed",
                                    data={
                                        "run_id": run_id,
                                        "thread_id": validated_thread_id,
                                        "tool": ev_name,
                                        "server_id": server_id,
                                        "error": str(err_val)[:1000],
                                        "tool_call_id": tc_id,
                                    },
                                )

                        elif event_type == "on_chat_model_stream":
                            chunk = ev_data.get("chunk")
                            if isinstance(chunk, AIMessageChunk) and chunk.content:
                                text = extract_message_text(chunk.content)
                                if text:
                                    accumulated_chunks.append(text)
                                    yield AgentStreamEvent(
                                        event="model_streaming",
                                        data={
                                            "run_id": run_id,
                                            "thread_id": validated_thread_id,
                                            "delta": text,
                                            "index": token_index,
                                        },
                                    )
                                    token_index += 1

                        elif event_type == "on_chat_model_end":
                            output = ev_data.get("output")
                            # 1. Check llm_output
                            if output and hasattr(output, "llm_output") and output.llm_output:
                                llm_out = output.llm_output
                                if "token_usage" in llm_out and isinstance(
                                    llm_out["token_usage"], dict
                                ):
                                    upstream_reported_usage = llm_out["token_usage"]
                                    p = int(upstream_reported_usage.get("prompt_tokens", 0))
                                    c = int(upstream_reported_usage.get("completion_tokens", 0))
                                    if p or c:
                                        total_prompt_tokens += p
                                        total_completion_tokens += c
                                        has_upstream_usage = True
                                    cost_val = upstream_reported_usage.get("cost")
                                    if cost_val is not None:
                                        try:
                                            total_upstream_cost += float(cost_val)
                                        except (ValueError, TypeError):
                                            pass
                                if "model_name" in llm_out and not selected_model:
                                    selected_model = str(llm_out["model_name"])

                            # 2. Extract from AIMessage (usage_metadata and response_metadata)
                            msg_obj = output if isinstance(output, AIMessage) else None
                            if (
                                not msg_obj
                                and hasattr(output, "generations")
                                and output.generations
                            ):
                                for gen_list in output.generations:
                                    items = gen_list if isinstance(gen_list, list) else [gen_list]
                                    for g in items:
                                        if hasattr(g, "message") and isinstance(
                                            g.message, AIMessage
                                        ):
                                            msg_obj = g.message
                                            break
                                    if msg_obj:
                                        break

                            if msg_obj:
                                if hasattr(msg_obj, "usage_metadata") and msg_obj.usage_metadata:
                                    um = msg_obj.usage_metadata
                                    p = int(um.get("input_tokens", 0))
                                    c = int(um.get("output_tokens", 0))
                                    if p or c:
                                        total_prompt_tokens += p
                                        total_completion_tokens += c
                                        has_upstream_usage = True
                                if (
                                    hasattr(msg_obj, "response_metadata")
                                    and msg_obj.response_metadata
                                ):
                                    rm = msg_obj.response_metadata
                                    if "model_name" in rm and not selected_model:
                                        selected_model = str(rm["model_name"])
                                    cost_val = rm.get("cost")
                                    if (
                                        cost_val is None
                                        and "cost_details" in rm
                                        and isinstance(rm["cost_details"], dict)
                                    ):
                                        cost_val = rm["cost_details"].get("upstream_inference_cost")
                                    if cost_val is not None:
                                        try:
                                            total_upstream_cost += float(cost_val)
                                        except (ValueError, TypeError):
                                            pass

                    final_state = await agent.aget_state(config)
                    checkpoint_id = None
                    if final_state and final_state.config:
                        checkpoint_id = final_state.config.get("configurable", {}).get(
                            "checkpoint_id"
                        )
                        if "todos" in final_state.values:
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

                    yield AgentStreamEvent(
                        event="checkpoint_saved",
                        data={
                            "run_id": run_id,
                            "thread_id": validated_thread_id,
                            "checkpoint_id": str(checkpoint_id) if checkpoint_id else None,
                        },
                    )

                    final_content = "".join(accumulated_chunks)
                    if not final_content and final_state and final_state.values.get("messages"):
                        messages = final_state.values["messages"]
                        for msg in reversed(messages):
                            if isinstance(msg, AIMessage):
                                text = extract_message_text(msg.content)
                                if text:
                                    final_content = text
                                    break

                    elapsed_ms = int((time.time() - start_time) * 1000)
                    effective_model = (
                        selected_model
                        or getattr(model, "_effective_model_name", None)
                        or model_name
                    )
                    if has_upstream_usage:
                        prompt_tokens = total_prompt_tokens
                        completion_tokens = total_completion_tokens
                        total_tokens = prompt_tokens + completion_tokens
                        up_cost = total_upstream_cost if total_upstream_cost > 0.0 else None
                        cost_usd = self.openrouter_service.calculate_cost(
                            model_id=effective_model,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                            upstream_cost=up_cost,
                            selected_model=effective_model,
                        )
                        usage = StreamUsage(
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                            total_tokens=total_tokens,
                            cost_usd=cost_usd,
                            upstream_cost=up_cost,
                            is_estimated=False,
                            cost_source="upstream" if up_cost is not None else "rate_card",
                            selected_model=effective_model,
                            requested_model=model_name,
                            cost_tier=effective_cost_tier,
                            session_id=None,
                        )
                    else:
                        prompt_tokens = max(1, len(model_req.message) // 4)
                        completion_tokens = max(1, len(final_content) // 4)
                        cost_usd = self.openrouter_service.calculate_cost(
                            model_id=effective_model,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                            selected_model=effective_model,
                        )
                        usage = StreamUsage(
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                            total_tokens=prompt_tokens + completion_tokens,
                            cost_usd=cost_usd,
                            upstream_cost=None,
                            is_estimated=True,
                            cost_source="character_estimate",
                            selected_model=effective_model,
                            requested_model=model_name,
                            cost_tier=effective_cost_tier,
                            session_id=None,
                        )

                    yield AgentStreamEvent(
                        event="run_completed",
                        data={
                            "run_id": run_id,
                            "thread_id": validated_thread_id,
                            "content": final_content,
                            "todos": [t.model_dump() for t in todos],
                            "usage": usage.model_dump(),
                            "elapsed_ms": elapsed_ms,
                            "checkpoint_id": str(checkpoint_id) if checkpoint_id else None,
                        },
                    )
                finally:
                    current_approval_context.reset(token)

            except asyncio.CancelledError:
                logger.info("Resumed agent run %s was cancelled by client", run_id)
                yield AgentStreamEvent(
                    event="run_cancelled",
                    data={
                        "run_id": run_id,
                        "thread_id": validated_thread_id,
                        "reason": "client_cancelled",
                    },
                )
                raise

            except Exception as e:
                logger.error(
                    "Resume run failed for thread %s: %s",
                    validated_thread_id,
                    e,
                    exc_info=True,
                )
                yield AgentStreamEvent(
                    event="run_failed",
                    data={
                        "run_id": run_id,
                        "thread_id": validated_thread_id,
                        "error": str(e),
                    },
                )

    async def resume_agent_execution(
        self,
        approval_id: str,
        decision: Literal["approve", "reject"],
        *,
        validated_thread_id: str | None = None,
        thread_id: str | None = None,
        reason: str | None = None,
        model_name_override: str | None = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        """Resume an interrupted agent run following human approval or rejection.

        Keyword-guarded convenience alias for canonical `resume_agent`.
        Ensures thread_id and validated_thread_id do not conflict.
        """
        if str(decision).lower() not in ("approve", "reject"):
            raise ValueError(
                f"Invalid decision '{decision}'. Decision must be strictly 'approve' or 'reject'."
            )
        if str(approval_id).lower() in ("approve", "reject"):
            raise ValueError(
                f"Invalid approval_id '{approval_id}': cannot be 'approve' or 'reject'. "
                "Did you pass decision before approval_id?"
            )
        if thread_id is not None and validated_thread_id is not None:
            if thread_id != validated_thread_id:
                raise ValueError(
                    f"Conflicting thread identifiers provided: thread_id='{thread_id}' != "
                    f"validated_thread_id='{validated_thread_id}'."
                )

        effective_thread_id = validated_thread_id or thread_id
        if not effective_thread_id:
            raise ValueError(
                "thread_id or validated_thread_id must be provided to resume agent execution."
            )
        async for ev in self.resume_agent(
            thread_id=effective_thread_id,
            approval_id=approval_id,
            decision=decision,
            reason=reason,
            model_name_override=model_name_override,
        ):
            yield ev

    async def get_thread_state(self, thread_id: str) -> AgentThreadStateResponse:
        """Retrieve persisted messages and todo plan items for a specific thread."""
        validated_thread_id = validate_thread_id(thread_id)

        if not self._is_initialized:
            await self.initialize()

        checkpointer = await self.checkpointer_manager.get_async_checkpointer()
        config = {"configurable": {"thread_id": validated_thread_id}}
        tuple_ = await checkpointer.aget_tuple(config)

        if tuple_ is None or not tuple_.checkpoint:
            return AgentThreadStateResponse(
                thread_id=validated_thread_id,
                messages=[],
                todos=[],
                checkpoint_id=None,
                exists=False,
                active_model=None,
            )

        reader_model = self.model_override or _StateReaderDummyModel()
        agent = self.create_agent(model=reader_model, checkpointer=checkpointer)
        state = await agent.aget_state(config)

        messages: list[ChatMessage] = []
        raw_messages = state.values.get("messages", []) if state else []
        for msg in raw_messages:
            if isinstance(msg, HumanMessage):
                text = extract_message_text(msg.content)
                messages.append(ChatMessage(role="user", content=text))
            elif isinstance(msg, AIMessage):
                text = extract_message_text(msg.content)
                # Only include assistant messages that have conversational content
                if text.strip():
                    messages.append(ChatMessage(role="assistant", content=text))
            elif isinstance(msg, SystemMessage):
                text = extract_message_text(msg.content)
                messages.append(ChatMessage(role="system", content=text))

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

        # Retrieve active model metadata from checkpoint metadata if present
        active_model = None
        if tuple_.metadata and isinstance(tuple_.metadata, dict):
            active_model = tuple_.metadata.get("model")

        # Reconstruct tool activities from checkpoint messages and durable approval store
        tool_activities: list[ToolActivityRecord] = []
        thread_approvals: list[ApprovalRecord] = []
        if self.approval_store:
            try:
                thread_approvals = await self.approval_store.get_thread_approvals(
                    validated_thread_id
                )
            except Exception as e:
                logger.warning(
                    "Could not query thread approvals for %s: %s", validated_thread_id, e
                )

        approval_by_tool_call_id = {
            appr.tool_call_id: appr for appr in thread_approvals if appr.tool_call_id
        }

        tool_messages_by_id: dict[str, Any] = {}
        for msg in raw_messages:
            if isinstance(msg, ToolMessage) or getattr(msg, "type", None) == "tool":
                t_cid = getattr(msg, "tool_call_id", "")
                if t_cid:
                    tool_messages_by_id[t_cid] = msg

        seen_tool_call_ids: set[str] = set()

        for msg in raw_messages:
            if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                for tc in msg.tool_calls:
                    tc_id = tc.get("id") or f"tc_{uuid.uuid4().hex[:8]}"
                    if tc_id in seen_tool_call_ids:
                        continue
                    seen_tool_call_ids.add(tc_id)
                    t_name = tc.get("name", "")
                    if t_name == "write_todos":
                        continue

                    server_id = "unknown"
                    tool_desc = ""
                    if self.mcp_gateway:
                        try:
                            server_id, _ = parse_namespaced_tool_id(t_name)
                        except Exception:
                            server_id = "unknown"
                        t_rec = self.mcp_gateway.registry.get_tool(t_name)
                        if t_rec:
                            tool_desc = t_rec.description

                    matched_appr = approval_by_tool_call_id.get(tc_id)
                    matched_tool_msg = tool_messages_by_id.get(tc_id)

                    status: ToolLifecycleState = "COMPLETED"
                    result_summary = None
                    error_message = None
                    started_at = None
                    completed_at = None
                    elapsed_ms = None
                    approval_id = None

                    if matched_appr:
                        approval_id = matched_appr.approval_id
                        if matched_appr.server_id:
                            server_id = matched_appr.server_id
                        started_at = matched_appr.dispatched_at or matched_appr.created_at
                        completed_at = matched_appr.completed_at
                        if started_at and completed_at:
                            elapsed_ms = int((completed_at - started_at).total_seconds() * 1000)

                        if matched_appr.status == "pending":
                            status = "AWAITING_APPROVAL"
                        elif matched_appr.status == "rejected":
                            status = "REJECTED"
                            error_message = (
                                matched_appr.rejection_reason or "Tool call was rejected by user."
                            )
                        elif matched_appr.status == "cancelled":
                            status = "CANCELLED"
                        elif matched_appr.dispatch_status == "uncertain":
                            status = "UNCERTAIN"
                            error_message = matched_appr.error_message
                        elif matched_appr.dispatch_status == "failed":
                            status = "FAILED"
                            error_message = matched_appr.error_message
                        elif matched_appr.dispatch_status == "completed":
                            status = "COMPLETED"
                            result_summary = matched_appr.result_summary
                        elif matched_appr.status == "approved":
                            status = "APPROVED"

                    if matched_tool_msg:
                        content_str = str(matched_tool_msg.content)
                        if (
                            getattr(matched_tool_msg, "status", None) == "error"
                            or "Security Violation:" in content_str
                        ):
                            status = "FAILED"
                            error_message = content_str
                        elif not result_summary:
                            result_summary = content_str
                    elif not matched_appr:
                        status = "EXECUTING"

                    tool_activities.append(
                        ToolActivityRecord(
                            tool_call_id=tc_id,
                            tool_id=t_name,
                            server_id=server_id,
                            tool_name=t_name,
                            description=tool_desc,
                            arguments=tc.get("args") or {},
                            status=status,
                            result_summary=result_summary,
                            error_message=error_message,
                            started_at=started_at,
                            completed_at=completed_at,
                            elapsed_ms=elapsed_ms,
                            approval_id=approval_id,
                        )
                    )

        # Include any pending approvals from approval_store not already attached
        for appr in thread_approvals:
            if appr.tool_call_id not in seen_tool_call_ids and appr.approval_id not in [
                t.approval_id for t in tool_activities if t.approval_id
            ]:
                seen_tool_call_ids.add(appr.tool_call_id)
                tool_activities.append(
                    ToolActivityRecord(
                        tool_call_id=appr.tool_call_id or f"appr_{appr.approval_id}",
                        tool_id=appr.tool_id,
                        server_id=appr.server_id,
                        tool_name=appr.tool_id,
                        description="",
                        arguments=appr.arguments,
                        status="AWAITING_APPROVAL"
                        if appr.status == "pending"
                        else (
                            "REJECTED"
                            if appr.status == "rejected"
                            else ("CANCELLED" if appr.status == "cancelled" else "COMPLETED")
                        ),
                        result_summary=appr.result_summary,
                        error_message=appr.error_message or appr.rejection_reason,
                        started_at=appr.created_at,
                        completed_at=appr.completed_at,
                        approval_id=appr.approval_id,
                    )
                )

        return AgentThreadStateResponse(
            thread_id=validated_thread_id,
            messages=messages,
            todos=todos,
            checkpoint_id=str(checkpoint_id) if checkpoint_id else None,
            exists=True,
            active_model=active_model,
            tool_calls=tool_activities,
        )

    async def get_status(self) -> AgentRuntimeStatusResponse:
        """Query agent runtime status, checkpointer state, and tool boundaries."""
        if not self._is_initialized:
            await self.initialize()

        allowed = sorted(list(ALLOWED_TOOLS))
        if self.mcp_gateway is not None:
            allowed = sorted(list(ALLOWED_TOOLS | set(self.mcp_gateway.get_executable_tools())))

        return AgentRuntimeStatusResponse(
            status="ready",
            checkpointer="sqlite",
            checkpoint_db_path=self.checkpointer_manager.db_path,
            security_profile="zero-trust-planning-only",
            allowed_tools=allowed,
            excluded_tools=sorted(list(EXCLUDED_TOOLS)),
        )
