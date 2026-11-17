import asyncio

from tests.test_publish_flow import FakeBot, _researcher


class RecordingLlm:
    def __init__(self, model):
        self.model = model
        self.inputs = []
        self.events = []

    async def invoke(self, prompt):
        self.events.append("start")
        self.inputs.append(prompt)
        await asyncio.sleep(0.01)
        self.events.append("end")
        return "ok"


def _bot_with(llm, cache=True):
    bot = FakeBot(_researcher())
    bot._forecasters = [llm]
    bot._prompt_cache = cache
    return bot


def test_claude_gets_cache_marker_and_first_call_warms_cache():
    llm = RecordingLlm("openrouter/anthropic/claude-opus-5.5")
    bot = _bot_with(llm)

    async def five():
        return await asyncio.gather(*(bot._reason("SAME LONG PROMPT") for _ in range(5)))

    out = asyncio.run(five())
    assert all(o.endswith("ok") for o in out)
    msg = llm.inputs[0]
    assert msg == [{"role": "user", "content": "SAME LONG PROMPT",
                    "cache_control": {"type": "ephemeral"}}]
    # Pierwsze wywołanie kończy się, zanim ruszą pozostałe.
    assert llm.events[:2] == ["start", "end"]


def test_non_claude_and_disabled_cache_send_plain_prompt():
    gpt = RecordingLlm("openrouter/openai/gpt-5.4")
    asyncio.run(_bot_with(gpt)._reason("P"))
    assert gpt.inputs == ["P"]

    claude = RecordingLlm("openrouter/anthropic/claude-opus-5.5")
    asyncio.run(_bot_with(claude, cache=False)._reason("P"))
    assert claude.inputs == ["P"]


def test_different_prompts_do_not_wait_for_each_other():
    llm = RecordingLlm("anthropic/claude-opus-5-5")
    bot = _bot_with(llm)

    async def two():
        await asyncio.gather(bot._reason("A"), bot._reason("B"))

    asyncio.run(two())
    assert llm.events[:2] == ["start", "start"]


def test_litellm_moves_cache_marker_into_openrouter_content_block():
    from litellm.llms.openrouter.chat.transformation import OpenrouterConfig

    msgs = [{"role": "user", "content": "P", "cache_control": {"type": "ephemeral"}}]
    body = OpenrouterConfig().transform_request(
        model="anthropic/claude-opus-5.5", messages=msgs, optional_params={},
        litellm_params={}, headers={},
    )
    assert body["messages"][0]["content"] == [
        {"type": "text", "text": "P", "cache_control": {"type": "ephemeral"}}
    ]
