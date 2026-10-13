"""WebSocket voice gateway: phone <-> this service <-> Gemini Live (through ADK run_live).

Protocol on /ws/voice?token=<Firebase ID token>[&ptt=1]
The caller's role (from the token) picks the agent: mechanics get the Live job agent, owners the owner agent
(read-only questions about the day, plus answering reorder asks).
  client -> server  binary: 16 kHz mono PCM16 mic audio
                    text JSON: {"type": "text", "text": ...}            typed fallback
                               {"type": "start"} / {"type": "stop"}     push-to-talk (ptt=1)
  server -> client  binary: 24 kHz mono PCM16 agent audio
                    text JSON: {"type": "transcript", "role": "mechanic"|"owner"|"agent", "text", "final"}
                               {"type": "tool", "name", "result"}
                               {"type": "turn_complete"} / {"type": "interrupted"}
                               {"type": "ignored", "reason": "no speech"}   a push-to-talk turn without speech
One live connection per mechanic: a newer one (another tab or phone) makes the older one close with code 4409.
Session state (current job) is loaded from and saved to Firestore, so any instance can serve the next connection.
"""

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from google.genai import types

from app import auth, config, speech, tools
from app.services import voice

log = logging.getLogger(__name__)
router = APIRouter()

APP_NAME = "garage_copilot"
MIC_MIME = "audio/pcm;rate=16000"
NOTICE_POLL_SECONDS = 2.0


def run_config(push_to_talk: bool):
    from google.adk.agents import RunConfig
    from google.adk.agents.run_config import StreamingMode

    realtime = None
    if push_to_talk:
        realtime = types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(disabled=True))
    speech = None
    if config.LIVE_VOICE:
        speech = types.SpeechConfig(voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=config.LIVE_VOICE)))
    return RunConfig(
        streaming_mode=StreamingMode.BIDI,
        speech_config=speech,
        response_modalities=[types.Modality.AUDIO],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        realtime_input_config=realtime,
        session_resumption=types.SessionResumptionConfig(),
        context_window_compression=types.ContextWindowCompressionConfig(sliding_window=types.SlidingWindow()),
    )


def agent_for(role: str):
    from app import agent

    return agent.build_owner_agent() if role == "owner" else agent.build_live_agent()


async def live_events(state: dict, queue, push_to_talk: bool):
    """Stream ADK events for one connection. Tests replace this with a stub."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    runner = Runner(app_name=APP_NAME, agent=agent_for(state["role"]), session_service=InMemorySessionService())
    session = await runner.session_service.create_session(app_name=APP_NAME, user_id=state["uid"], state=state)
    async for event in runner.run_live(user_id=state["uid"], session_id=session.id,
                                       live_request_queue=queue, run_config=run_config(push_to_talk)):
        yield event


def new_queue():
    from google.adk.agents import LiveRequestQueue

    return LiveRequestQueue()


MAX_TURN_BYTES = 60 * 16000 * 2  # a push-to-talk turn is capped at 60 s


def send_turn(queue, pcm: bytes) -> None:
    queue.send_activity_start()
    for i in range(0, len(pcm), 3200):  # 100 ms chunks
        queue.send_realtime(types.Blob(data=pcm[i:i + 3200], mime_type=MIC_MIME))
    queue.send_activity_end()


async def upstream(ws: WebSocket, queue, push_to_talk: bool = False) -> None:
    # Push-to-talk: the held turn is kept here and sent to Gemini on release only if it contains speech.
    # Gemini answers every activity start/end pair, even a silent one, and could guess an action from the
    # job in context; a tap, silence or noise must never become a command. (In this mode Gemini only answers
    # after the release anyway, so holding the audio here costs little.) Hands-free streams straight through.
    turn = None
    while True:
        msg = await ws.receive()
        if msg["type"] == "websocket.disconnect":
            return
        if msg.get("bytes"):
            if not push_to_talk:
                queue.send_realtime(types.Blob(data=msg["bytes"], mime_type=MIC_MIME))
            elif turn is not None and len(turn) < MAX_TURN_BYTES:
                turn += msg["bytes"]
        elif msg.get("text"):
            data = json.loads(msg["text"])
            if data.get("type") == "text":
                queue.send_content(types.Content(role="user", parts=[types.Part(text=data["text"])]))
            elif data.get("type") == "start":
                if push_to_talk:
                    turn = bytearray()
                else:
                    queue.send_activity_start()
            elif data.get("type") == "stop":
                if not push_to_talk:
                    queue.send_activity_end()
                elif turn is not None:
                    pcm, turn = bytes(turn), None
                    if speech.has_speech(pcm):
                        send_turn(queue, pcm)
                    else:
                        log.info("push-to-talk turn dropped: %d ms voiced", speech.voiced_ms(pcm))
                        await ws.send_json({"type": "ignored", "reason": "no speech"})


class Replaced(Exception):
    """This mechanic opened the voice screen somewhere else."""


def audio_parts(event):
    if not (event.content and event.content.parts):
        return []
    return [p.inline_data.data for p in event.content.parts
            if p.inline_data and p.inline_data.data and (p.inline_data.mime_type or "").startswith("audio/")]


async def downstream(ws: WebSocket, events, who: dict, state: dict) -> None:
    streamed = False  # audio already sent in this turn
    async for event in events:
        # Each audio chunk is sent once. Streamed chunks come in events that are not marked partial=False;
        # an event explicitly marked partial=False is an aggregate of the turn, so its audio is skipped
        # when the turn already streamed audio (otherwise the mechanic hears the reply twice).
        audio = audio_parts(event)
        if audio and not (event.partial is False and streamed):
            for chunk in audio:
                await ws.send_bytes(chunk)
            streamed = True
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.function_response:
                    await ws.send_json({"type": "tool", "name": part.function_response.name,
                                        "result": part.function_response.response})
        speaker = "owner" if who["role"] == "owner" else "mechanic"
        for role, tr in ((speaker, event.input_transcription), ("agent", event.output_transcription)):
            if tr and tr.text:
                await ws.send_json({"type": "transcript", "role": role, "text": tr.text, "final": bool(tr.finished)})
        delta = getattr(event.actions, "state_delta", None) or {}
        if delta.get(tools.CURRENT_JOB) and delta[tools.CURRENT_JOB] != state.get(tools.CURRENT_JOB):
            state[tools.CURRENT_JOB] = delta[tools.CURRENT_JOB]
            await asyncio.to_thread(voice.save_session, who, state[tools.CURRENT_JOB])
        if event.interrupted:
            await ws.send_json({"type": "interrupted"})
        if event.turn_complete:
            await ws.send_json({"type": "turn_complete"})
        if event.interrupted or event.turn_complete:
            streamed = False


async def notices(queue, who: dict, conn: str) -> None:
    """Speak messages meant for this mechanic (e.g. "Ramesh approved. Go ahead."). Also stops this
    connection when the mechanic has opened a newer one, so two Gemini sessions never answer the same mic."""
    while True:
        if not await asyncio.to_thread(voice.is_current, who, conn):
            raise Replaced()
        if who["role"] == "owner":  # the owner sees updates on the dashboard; nothing to speak
            await asyncio.sleep(NOTICE_POLL_SECONDS)
            continue
        for m in await asyncio.to_thread(voice.take_headset_messages, who):
            queue.send_content(types.Content(role="user", parts=[types.Part(text=f"[notice] {m['text']}")]))
        await asyncio.sleep(NOTICE_POLL_SECONDS)


@router.websocket("/ws/voice")
async def voice_ws(ws: WebSocket, token: str = "", ptt: int = 0):
    await ws.accept()
    try:
        who = auth.to_actor(auth.claims_from_header(f"Bearer {token}"))
    except HTTPException as e:
        await ws.close(code=4401 if e.status_code == 401 else 4403, reason=str(e.detail))
        return
    conn = uuid.uuid4().hex[:12]
    await asyncio.to_thread(voice.claim_session, who, conn)
    state = await asyncio.to_thread(voice.load_session, who)
    queue = new_queue()
    tasks = [
        asyncio.create_task(upstream(ws, queue, bool(ptt))),
        asyncio.create_task(downstream(ws, live_events(state, queue, bool(ptt)), who, state)),
        asyncio.create_task(notices(queue, who, conn)),
    ]
    log.info("voice session %s opened for %s/%s", conn, who["garage_id"], who["uid"])
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            if isinstance(task.exception(), Replaced):
                await ws.close(code=4409, reason="Opened on another screen")
            elif task.exception() and not isinstance(task.exception(), WebSocketDisconnect):
                log.error("voice session failed", exc_info=task.exception())
    finally:
        for task in tasks:
            task.cancel()
        queue.close()
        log.info("voice session %s closed for %s/%s", conn, who["garage_id"], who["uid"])
