"""WebSocket voice gateway: phone <-> this service <-> Gemini Live (through ADK run_live).

Protocol on /ws/voice?token=<Firebase ID token>[&ptt=1][&lang=en|hi|mr]
lang pins the reply language (the screen's language picker); without it the agent follows the speaker (C11).
The caller's role (from the token) picks the agent: mechanics get the Live job agent, owners the owner agent
(read-only questions about the day, plus answering reorder asks), and a front-desk call token ("call.…", from
POST /api/call/start or /api/j/{token}/call) the front desk agent for a customer calling the garage (C15).
  client -> server  binary: 16 kHz mono PCM16 mic audio
                    text JSON: {"type": "text", "text": ...}            typed fallback
                               {"type": "start"} / {"type": "stop"}     push-to-talk (ptt=1)
  server -> client  binary: 24 kHz mono PCM16 agent audio
                    text JSON: {"type": "transcript", "role": "mechanic"|"owner"|"agent", "text", "final"}
                               {"type": "tool", "name", "result"}
                               {"type": "turn_complete"} / {"type": "interrupted"}
                               {"type": "ignored", "reason": "no speech"}   a push-to-talk turn without speech
                               {"type": "blocked", "reason": "off_topic"}   the topic guard cut an off-topic turn (C20)
One live connection per mechanic: a newer one (another tab or phone) makes the older one close with code 4409.
Session state (current job) is loaded from and saved to Firestore, so any instance can serve the next connection.
"""

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from google.genai import types

from app import auth, config, consent, language, links, speech, tools, topic
from app.services import core, frontdesk, voice

log = logging.getLogger(__name__)
router = APIRouter()

APP_NAME = "garage_copilot"
MIC_MIME = "audio/pcm;rate=16000"
NOTICE_POLL_SECONDS = 2.0


def run_config(push_to_talk: bool, lang: str = ""):
    from google.adk.agents import RunConfig
    from google.adk.agents.run_config import StreamingMode

    realtime = None
    if push_to_talk:
        realtime = types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(disabled=True))
    speech = None
    voice_config = None
    if config.LIVE_VOICE:
        voice_config = types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=config.LIVE_VOICE))
    # A pinned language goes into the instruction always, and into speech_config.language_code only when
    # LIVE_LANGUAGE_CODE=1: native-audio Live models choose the language themselves and reject language_code
    # ("Unsupported language code"); half-cascade Live models use it.
    code = language.LANGUAGE_CODES.get(language.pinned(lang)) if config.LIVE_LANGUAGE_CODE else None
    if voice_config or code:
        speech = types.SpeechConfig(voice_config=voice_config, language_code=code)
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

    if role == "caller":
        return agent.build_front_desk_agent()
    return agent.build_owner_agent() if role == "owner" else agent.build_live_agent()


async def live_events(state: dict, queue, push_to_talk: bool):
    """Stream ADK events for one connection. Tests replace this with a stub."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    runner = Runner(app_name=APP_NAME, agent=agent_for(state["role"]), session_service=InMemorySessionService())
    session = await runner.session_service.create_session(app_name=APP_NAME, user_id=state["uid"], state=state)
    async for event in runner.run_live(user_id=state["uid"], session_id=session.id, live_request_queue=queue,
                                       run_config=run_config(push_to_talk, state.get("pinned_lang", ""))):
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


class Guard:
    """Topic guard for one connection (C20): the layer that enforces "garage work only" from outside the model.
    A finished user utterance (and once per turn the agent's own words, if they run long) is checked alongside the
    reply. Off-topic → the rest of this turn's agent audio and words are dropped, the phone is told to stop playing,
    and the agent is asked to say one line instead. A caller who keeps at it has the call ended."""

    REPLY_WORDS_TO_CHECK = 18  # garage replies are a sentence; a long answer gets checked once
    GOODBYE_SECONDS = 4  # a caller's goodbye plays before the call closes

    def __init__(self, ws: WebSocket, queue, who: dict):
        self.ws, self.queue, self.who = ws, queue, who
        self.blocking = False  # dropping the rest of the current turn
        self.in_turn = False  # the agent is mid-reply
        self.awaiting_reply = False  # a request was heard and its reply hasn't finished yet
        self.checked_reply = False
        self.strikes = 0
        self.ending = False  # a caller's call ends after this turn
        self.tasks = set()

    def check(self, text: str, source: str) -> None:
        """Check in the background; normal turns never wait for it."""
        if not config.TOPIC_GUARD or not topic.worth_checking(text):
            return
        task = asyncio.create_task(self._check(text, source))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def reply_grew(self, said_so_far: str) -> None:
        if not self.checked_reply and len(said_so_far.split()) >= self.REPLY_WORDS_TO_CHECK:
            self.checked_reply = True
            self.check(said_so_far, "agent reply")

    async def _check(self, text: str, source: str) -> None:
        if await topic.on_topic(text, self.who["role"]) is False and not self.blocking:
            await self.block(text, source)

    async def block(self, text: str, source: str, typed: bool = False) -> None:
        self.strikes += 1
        # Drop the reply to this request, whether it has started yet or not; a reply that already finished has
        # nothing left to drop (then only the refusal follows).
        self.blocking = (self.in_turn or self.awaiting_reply) and not typed
        log.warning("off-topic %s blocked for %s/%s: %r", source, self.who["garage_id"], self.who["uid"], text[:120])
        await self.ws.send_json({"type": "blocked", "reason": "off_topic", "typed": typed})
        await asyncio.to_thread(self._record, text, source)
        if typed:
            return  # never reached Gemini: nothing to take back
        self.ending = self.who["role"] == "caller" and self.strikes >= config.TOPIC_STRIKES_TO_END_CALL
        note = topic.END_CALL_NOTE if self.ending else topic.REFUSAL_NOTE
        self.queue.send_content(types.Content(role="user", parts=[types.Part(text=note)]))

    def _record(self, text: str, source: str) -> None:
        try:
            core.audit(self.who["garage_id"], self.who, "topic_blocked", {"where": source, "text": text[:200]})
            if self.who["role"] == "caller":
                frontdesk.note_action(self.who, self.who["garage_id"], "Off-topic request blocked")
        except Exception:
            log.exception("could not record a blocked off-topic request")

    def heard(self, text: str) -> None:
        self.awaiting_reply = True
        self.check(text, "request")

    def turn_over(self) -> None:
        self.blocking = self.in_turn = self.checked_reply = self.awaiting_reply = False


async def upstream(ws: WebSocket, queue, push_to_talk: bool = False, guard: Guard | None = None) -> None:
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
                # Typed text is checked BEFORE it reaches Gemini: an off-topic request is never sent (C20)
                if guard and await topic.on_topic(data["text"], guard.who["role"]) is False:
                    await guard.block(data["text"], "typed", typed=True)
                    continue
                if guard:
                    consent.heard(guard.who["uid"], data["text"])
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


def check_language(queue, state: dict, heard: str, said: str) -> bool:
    """After a turn in Auto mode: a reply clearly in another script than what was heard is logged, and a one-line
    reminder is added to the session for the next turn (partial content: Gemini doesn't answer it)."""
    if state.get("pinned_lang") or not language.mismatch(heard, said):
        return False
    log.warning("language mismatch: heard %r, said %r", heard[:80], said[:80])
    if queue is not None:
        queue.send_content(types.Content(role="user", parts=[types.Part(text=language.reminder(heard))]), partial=True)
    return True


async def downstream(ws: WebSocket, events, who: dict, state: dict, queue=None, guard: Guard | None = None) -> None:
    streamed = False  # audio already sent in this turn
    heard, said = [], []  # this turn's final transcriptions, for the language check
    guard = guard or Guard(ws, queue, who)
    async for event in events:
        # Each audio chunk is sent once. Streamed chunks come in events that are not marked partial=False;
        # an event explicitly marked partial=False is an aggregate of the turn, so its audio is skipped
        # when the turn already streamed audio (otherwise the mechanic hears the reply twice).
        audio = audio_parts(event)
        if audio:
            guard.in_turn = True
        if audio and not (event.partial is False and streamed) and not guard.blocking:
            for chunk in audio:
                await ws.send_bytes(chunk)
            streamed = True
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.function_response:
                    await ws.send_json({"type": "tool", "name": part.function_response.name,
                                        "result": part.function_response.response})
        speaker = who["role"] if who["role"] in ("owner", "caller") else "mechanic"
        for role, tr in ((speaker, event.input_transcription), ("agent", event.output_transcription)):
            if tr and tr.text:
                if role == "agent":
                    guard.in_turn = True
                    if guard.blocking:
                        continue  # the off-topic answer being cut off: don't show it either
                await ws.send_json({"type": "transcript", "role": role, "text": tr.text, "final": bool(tr.finished)})
                (said if role == "agent" else heard).append(tr.text)
                if role != "agent" and tr.finished:
                    guard.heard(tr.text)
                    consent.heard(who["uid"], tr.text)  # a "yes" to the web-search offer must be the mechanic's own (C19)
                elif role == "agent":
                    guard.reply_grew(" ".join(said))
                if role == "caller" and tr.finished:  # the caller's words become the call's summary for the owner
                    await asyncio.to_thread(frontdesk.note_heard, who["garage_id"], who["call_id"], tr.text)
        delta = getattr(event.actions, "state_delta", None) or {}
        if delta.get(tools.CURRENT_JOB) and delta[tools.CURRENT_JOB] != state.get(tools.CURRENT_JOB):
            state[tools.CURRENT_JOB] = delta[tools.CURRENT_JOB]
            await asyncio.to_thread(voice.save_session, who, state[tools.CURRENT_JOB])
        if event.interrupted:
            await ws.send_json({"type": "interrupted"})
        if event.turn_complete:
            await ws.send_json({"type": "turn_complete"})
            check_language(queue, state, " ".join(heard), " ".join(said))
            heard, said = [], []
        if event.interrupted or event.turn_complete:
            streamed = False
            guard.turn_over()
        if event.turn_complete and guard.ending:
            await asyncio.sleep(guard.GOODBYE_SECONDS)  # let the goodbye play
            await ws.close(code=1000, reason="Call ended: only garage questions on this line")
            return


async def notices(queue, who: dict, conn: str) -> None:
    """Speak messages meant for this mechanic (e.g. "Ramesh approved. Go ahead."). Also stops this
    connection when the mechanic has opened a newer one, so two Gemini sessions never answer the same mic."""
    while True:
        if not await asyncio.to_thread(voice.is_current, who, conn):
            raise Replaced()
        if who["role"] in ("owner", "caller"):  # nothing to speak: the owner sees updates on the dashboard
            await asyncio.sleep(NOTICE_POLL_SECONDS)
            continue
        for m in await asyncio.to_thread(voice.take_headset_messages, who):
            queue.send_content(types.Content(role="user", parts=[types.Part(text=f"[notice] {m['text']}")]))
        await asyncio.sleep(NOTICE_POLL_SECONDS)


@router.websocket("/ws/voice")
async def voice_ws(ws: WebSocket, token: str = "", ptt: int = 0, lang: str = ""):
    await ws.accept()
    if token.startswith("call."):  # a customer calling the garage (front desk)
        try:
            call = links.read_caller_token(token)
        except links.BadLink as e:
            await ws.close(code=4401, reason=str(e))
            return
        who = frontdesk.caller(call["garage_id"], call["phone"], call["verified"], call["call_id"], call["job_id"])
    else:
        try:
            who = auth.to_actor(auth.claims_from_header(f"Bearer {token}"))
        except HTTPException as e:
            await ws.close(code=4401 if e.status_code == 401 else 4403, reason=str(e.detail))
            return
    conn = uuid.uuid4().hex[:12]
    await asyncio.to_thread(voice.claim_session, who, conn)
    state = await asyncio.to_thread(voice.load_session, who)
    state["pinned_lang"] = language.pinned(lang)
    if who["role"] == "caller":
        state.update(phone=who["phone"], verified=who["verified"], call_id=who["call_id"], call_job=who["job_id"],
                     current_job="")
    queue = new_queue()
    guard = Guard(ws, queue, who)
    tasks = [
        asyncio.create_task(upstream(ws, queue, bool(ptt), guard)),
        asyncio.create_task(downstream(ws, live_events(state, queue, bool(ptt)), who, state, queue, guard)),
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
        if who["role"] == "caller":
            await asyncio.to_thread(frontdesk.end_call, who["garage_id"], who["call_id"])
        log.info("voice session %s closed for %s/%s", conn, who["garage_id"], who["uid"])
