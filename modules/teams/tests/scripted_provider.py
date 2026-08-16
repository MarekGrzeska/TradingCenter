"""A model provider that answers from a script, and records what it was asked.

Nothing here reaches OpenAI: `provider.py` is the one file that does, and it is covered by
its own shape rather than by calls that cost money and answer differently every time. What
the runner needs from a provider is a stream of chunks, so a test hands it exactly that.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field

from teams.provider import ProviderChunk, TextDelta, ToolCallRequest, ToolRound, UsageReport
from teams.tools import ToolDescriptor


@dataclass(frozen=True)
class Ask:
    """One call the runner made, as the provider saw it."""

    model: str
    system_prompt: str
    briefing: str
    tool_names: tuple[str, ...]
    rounds: int


Script = Callable[[Ask], Sequence[ProviderChunk]]


def says(text: str, *, tokens: tuple[int, int] | None = (100, 20)) -> Script:
    """Answers with one piece of text and a usage report, whatever it was asked."""

    def script(ask: Ask) -> Sequence[ProviderChunk]:
        del ask
        usage = (
            UsageReport(None, None, None, None)
            if tokens is None
            else UsageReport(tokens[0], tokens[1], None, None)
        )
        return [TextDelta(text), usage]

    return script


def asks_for_tool(name: str, arguments: dict, *, then: str) -> Script:
    """Asks for one tool on the first call, answers on the next — the shape of an agent
    that checked something before concluding."""

    def script(ask: Ask) -> Sequence[ProviderChunk]:
        if ask.rounds == 0:
            return [ToolCallRequest(id="call-1", name=name, arguments=arguments), UsageReport(10, 2, None, None)]
        return [TextDelta(then), UsageReport(20, 4, None, None)]

    return script


def always_asks_for_tool(name: str) -> Script:
    """Never stops asking — what the round ceiling exists for."""

    def script(ask: Ask) -> Sequence[ProviderChunk]:
        return [
            ToolCallRequest(id=f"call-{ask.rounds}", name=name, arguments={}),
            TextDelta(f"round {ask.rounds}. "),
            UsageReport(5, 1, None, None),
        ]

    return script


def breaks(message: str = "the provider broke") -> Script:
    def script(ask: Ask) -> Sequence[ProviderChunk]:
        del ask
        raise RuntimeError(message)

    return script


@dataclass
class ScriptedProvider:
    """`ModelProvider` for tests. `by_role` picks a script per agent; anything not named
    there falls back to `default`."""

    default: Script = field(default_factory=lambda: says("done."))
    by_role: dict[str, Script] = field(default_factory=dict)
    asks: list[Ask] = field(default_factory=list)

    def stream(
        self,
        *,
        model: str,
        system_prompt: str,
        briefing: str,
        tools: Sequence[ToolDescriptor] = (),
        rounds: Sequence[ToolRound] = (),
    ) -> AsyncIterator[ProviderChunk]:
        ask = Ask(
            model=model,
            system_prompt=system_prompt,
            briefing=briefing,
            tool_names=tuple(tool.name for tool in tools),
            rounds=len(rounds),
        )
        self.asks.append(ask)
        script = self._script_for(system_prompt)

        async def chunks() -> AsyncIterator[ProviderChunk]:
            for chunk in script(ask):
                yield chunk

        return chunks()

    def _script_for(self, system_prompt: str) -> Script:
        for role, script in self.by_role.items():
            # The role is what `loop.system_prompt_for` puts in the first line, which is
            # the only thing distinguishing one agent's call from another's here.
            if f"You are the {role}" in system_prompt:
                return script
        return self.default

    def asks_for(self, role: str) -> list[Ask]:
        return [ask for ask in self.asks if f"You are the {role}" in ask.system_prompt]
