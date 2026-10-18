"""The one call to a model this package makes: a sentence, the instructions, and a schema the answer must fit. No stream, no
tools, no history — which is why `tc-openai`, built for all three, is not what stands here."""

from __future__ import annotations

from .config import Settings
from .drafts import DRAFT_SCHEMA, Answer, Unusable


class OpenAIDrafter:
    def __init__(self, client, model: str) -> None:
        self._client = client
        self._model = model

    async def draft(self, system: str, sentence: str) -> Answer:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": sentence}],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "alert_rule_draft", "schema": DRAFT_SCHEMA, "strict": True},
            },
        )
        content = response.choices[0].message.content or ""
        if not content.strip():
            raise Unusable("the model answered with nothing")
        usage = response.usage
        return Answer(
            payload=content,
            model=self._model,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )


def build(settings: Settings) -> OpenAIDrafter | None:
    """The drafter this deployment is configured for, or `None`: without a key everything works but drafting."""
    if not settings.drafting:
        return None
    from openai import AsyncOpenAI

    return OpenAIDrafter(AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url), settings.draft_model)
