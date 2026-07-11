"""Headlessly dispatch the agent into a fresh room to reproduce session crashes
without a browser. Usage: .venv/bin/python tests/dispatch_probe.py
"""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env.local")

from livekit import api


async def main() -> None:
    room = f"probe-{uuid.uuid4().hex[:8]}"
    lk = api.LiveKitAPI()
    dispatch = await lk.agent_dispatch.create_dispatch(
        api.CreateAgentDispatchRequest(agent_name="paymanshu-voice", room=room)
    )
    print(f"dispatched to room={room} dispatch_id={dispatch.id}")
    await lk.aclose()


asyncio.run(main())
