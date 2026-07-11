"""BISECT BASELINE — yesterday's known-good agent wiring (plain models,
tool-based retrieval, no fallbacks, no observability). If THIS crashes too,
the regression is environmental, not in today's code changes.

Run: .venv/bin/python tests/main_baseline.py start
"""

import os
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import (
    AgentServer,
    AgentSession,
    Agent,
    RunContext,
    TurnHandlingOptions,
    function_tool,
)
from livekit.plugins import google, deepgram, cartesia, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from resume_context import get_resume_index

load_dotenv(Path(__file__).parent.parent / ".env.local")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice-agent-baseline")

INSTRUCTIONS = """\
You are Paymanshu Sharma, speaking in first person about your own experience.
Keep responses concise. No markdown. Use lookup_resume for details.
"""


class PaymanshuAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=INSTRUCTIONS)

    @function_tool()
    async def lookup_resume(self, context: RunContext, query: str) -> str:
        """Search the resume."""
        return get_resume_index().search(query, top_k=3)


server = AgentServer()


@server.rtc_session(agent_name="paymanshu-voice")
async def voice_agent(ctx: agents.JobContext):
    logger.info(f"[baseline] New session in room: {ctx.room.name}")

    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="en"),
        llm=google.LLM(model="gemini-3.1-flash-lite"),
        tts=cartesia.TTS(
            model="sonic-3",
            voice=os.environ.get("CARTESIA_VOICE_ID", "79a125e8-cd45-4c13-8a67-188112f4dd22"),
        ),
        vad=silero.VAD.load(),
        turn_handling=TurnHandlingOptions(turn_detection=MultilingualModel()),
    )

    await session.start(room=ctx.room, agent=PaymanshuAgent())

    try:
        await session.generate_reply(instructions="Greet briefly as Paymanshu.")
    except Exception as e:
        logger.warning(f"generate_reply failed: {e}")
        await session.say("Hey! I'm Paymanshu.")

    logger.info("Agent session started successfully")


if __name__ == "__main__":
    agents.cli.run_app(server)
