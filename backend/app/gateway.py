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
                               {"type": "blocked", "reason": "safety"}      Model Armor flagged it (C18)
One live connection per mechanic: a newer one (another tab or phone) makes the older one close with code 4409.
Session state (current job) is loaded from and saved to Firestore, so any instance can serve the next connection.
"""

import asyncio
import json
import logging
import time
import uuid

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from google.genai import types

from app import armor, auth, config, consent, language, links, speech, tools, topic
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
    and the agent is asked to say one line instead. A caller who keeps at it has the call ended.
    One exchange (a request and the reply to it) costs one strike at most, however many of its checks come back
    off-topic. Typed text is checked before it is sent on, in the background so the mic keeps streaming.
    Model Armor (C18) uses the same points when MODEL_ARMOR_TEMPLATE is set: a caller's finished utterances (a flag
    costs a strike, like an off-topic request), typed text (alongside the topic check, so no extra wait), and the
    agent's reply after each turn (logged only: it has been spoken already)."""

    REPLY_WORDS_TO_CHECK = 18  # garage replies are a sentence; a long answer gets checked once
    GOODBYE_SECONDS = 4  # a caller's goodbye plays before the call closes
    LATE_HEARD_SECONDS = 2  # a request's words this soon after its reply ended are late, not a new request

    def __init__(self, ws: WebSocket, queue, who: dict):
        self.ws, self.queue, self.who = ws, queue, who
        self.blocking = False  # dropping the rest of the current turn
        self.in_turn = False  # the agent is mid-reply
        self.awaiting_reply = False  # a request was heard and its reply hasn't finished yet
        self.checked_reply = False
        self.strikes = 0
        self.exchange = 0  # counts agent turns; each check belongs to the exchange it was about
        self.heard_now = False  # the request of this exchange has been heard
        self.unheard = None  # (exchange, ended at): a reply that finished before its request's words came in
        self.struck = -1  # the last exchange that cost a strike
        self.ending = False  # a caller's call ends once the goodbye has played
        self.goodbye_heard = False  # agent output went out after the goodbye was asked for
        self.tasks = set()

    def check(self, text: str, source: str) -> None:
        """Check in the background; normal turns never wait for it."""
        if not config.TOPIC_GUARD or not topic.worth_checking(text):
            return
        self._start(self._check(text, source, self.exchange_of(source)))

    def _start(self, work) -> None:
        task = asyncio.create_task(work)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def exchange_of(self, source: str) -> int:
        """A request heard just after its reply ended (Live can send the words late) belongs to that reply's
        exchange, not the next one. Later than that, it's a new request (e.g. after a refusal or a notice)."""
        if source == "request" and not self.in_turn and self.unheard is not None:
            exchange, ended = self.unheard
            if time.monotonic() - ended <= self.LATE_HEARD_SECONDS:
                return exchange
        return self.exchange

    def typed(self, text: str) -> None:
        """Typed text reaches Gemini only once it passed the check (C20); the receive loop doesn't wait for it."""
        self._start(self._typed(text))

    async def _typed(self, text: str) -> None:
        screened, on = await asyncio.gather(armor.screen_prompt(text, f"typed by {self.who['role']}"),
                                            topic.on_topic(text, self.who["role"]))
        if screened["ok"] is False:  # Model Armor (C18): never sent; if it can't be asked, the text goes on (logged)
            await self.block(text, "typed", typed=True, reason="safety", reasons=screened["reasons"])
            return
        if on is False:
            await self.block(text, "typed", typed=True)
            return
        consent.heard(self.who["uid"], text)
        self.queue.send_content(types.Content(role="user", parts=[types.Part(text=text)]))

    def reply_grew(self, said_so_far: str) -> None:
        if not self.checked_reply and len(said_so_far.split()) >= self.REPLY_WORDS_TO_CHECK:
            self.checked_reply = True
            self.check(said_so_far, "agent reply")

    async def _check(self, text: str, source: str, exchange: int) -> None:
        on = await topic.on_topic(text, self.who["role"], reply=source == "agent reply")
        if on is False and exchange != self.struck:
            self.struck = exchange
            await self.block(text, source)

    def screen_caller(self, text: str) -> None:
        """Model Armor on a caller's finished words (C18), in the background. Flagged → refused like an off-topic
        request (same strikes, so two flagged turns end the call); if Model Armor can't be asked, the turn goes on."""
        if self.who["role"] == "caller" and armor.enabled():
            self._start(self._screen_caller(text, self.exchange_of("request")))

    async def _screen_caller(self, text: str, exchange: int) -> None:
        screened = await armor.screen_prompt(text, "caller")
        if screened["ok"] is False and exchange != self.struck:
            self.struck = exchange
            await self.block(text, "caller", reason="safety", reasons=screened["reasons"])

    def screen_reply(self, text: str) -> None:
        """Model Armor on the agent's words after the turn (C18): logged and counted, never blocked (already spoken)."""
        if armor.enabled() and text.strip():
            self._start(self._screen_reply(text))

    async def _screen_reply(self, text: str) -> None:
        screened = await armor.screen_response(text, f"{self.who['role']} agent reply")
        if screened["ok"] is False:
            await asyncio.to_thread(armor.record, self.who, "agent reply", screened["reasons"], "logged (already spoken)",
                                    text)

    async def block(self, text: str, source: str, typed: bool = False, reason: str = "off_topic",
                    reasons: list[str] | None = None) -> None:
        self.strikes += 1
        # Drop the reply to this request, whether it has started yet or not; a reply that already finished has
        # nothing left to drop (then only the refusal follows).
        self.blocking = (self.in_turn or self.awaiting_reply) and not typed
        log.warning("%s %s blocked for %s/%s: %r", reason, source, self.who["garage_id"], self.who["uid"], text[:120])
        try:
            await self.ws.send_json({"type": "blocked", "reason": reason, "typed": typed})
            open_ = True
        except Exception:
            open_ = False  # the caller already hung up: nobody left to refuse, but the owner's records still get it
        if open_ and not typed:  # typed text never reached Gemini: nothing to take back
            self.ending = self.who["role"] == "caller" and self.strikes >= config.TOPIC_STRIKES_TO_END_CALL
            note = topic.END_CALL_NOTE if self.ending else topic.REFUSAL_NOTE
            self.queue.send_content(types.Content(role="user", parts=[types.Part(text=note)]))
        if reason == "safety":
            await asyncio.to_thread(self._record_safety, text, source, reasons or [], typed)
        else:
            await asyncio.to_thread(self._record, text, source)  # after the refusal, so it isn't delayed

    def _record_safety(self, text: str, source: str, reasons: list[str], typed: bool) -> None:
        """Model Armor flag (C18): an "AI safety" line in the owner's feed, and on the Calls list for a caller."""
        action = "not sent" if typed else "call ended" if self.ending else "refused"
        armor.record(self.who, source, reasons, action, text)
        if self.who["role"] == "caller":
            try:
                frontdesk.note_action(self.who, self.who["garage_id"],
                                      "Call ended after a safety check" if self.ending else "Request failed a safety check")
            except Exception:
                log.exception("could not note a safety flag on the call")

    def _record(self, text: str, source: str) -> None:
        try:
            core.audit(self.who["garage_id"], self.who, "topic_blocked", {"where": source, "text": text[:200]})
            if self.who["role"] == "caller":
                frontdesk.note_action(self.who, self.who["garage_id"], "Off-topic request blocked")
        except Exception:
            log.exception("could not record a blocked off-topic request")

    def heard(self, text: str) -> None:
        self.check(text, "request")
        self.screen_caller(text)
        if self.exchange_of("request") == self.exchange:
            self.heard_now = True
            self.awaiting_reply = True
        self.unheard = None

    def spoke(self) -> None:
        """Agent audio or words went out to the phone."""
        self.in_turn = True
        if self.ending and not self.blocking:
            self.goodbye_heard = True

    def hang_up_now(self) -> bool:
        """After a turn: the caller's call ends once the goodbye turn itself is over, not the blocked one."""
        return self.ending and self.goodbye_heard

    def turn_over(self) -> None:
        self.unheard = (self.exchange, time.monotonic()) if self.in_turn and not self.heard_now else None
        self.exchange += 1
        self.blocking = self.in_turn = self.checked_reply = self.awaiting_reply = self.heard_now = False


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
                if guard:
                    guard.typed(data["text"])
                else:
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
            guard.spoke()
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
                    guard.spoke()
                await ws.send_json({"type": "transcript", "role": role, "text": tr.text, "final": bool(tr.finished)})
                (said if role == "agent" else heard).append(tr.text)
                if role != "agent" and tr.finished:
                    guard.heard(tr.text)
                    consent.heard(who["uid"], tr.text)  # a "yes" to the web-search offer must be the mechanic's own (C19)
                elif role == "agent":
                    guard.reply_grew(" ".join(said))
                    if who["role"] == "mechanic":
                        consent.agent_said(who["uid"], " ".join(said))  # "Shall I search online?" is the offer
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
            guard.screen_reply(" ".join(said))
            heard = []
        if event.interrupted or event.turn_complete:
            streamed = False
            said = []  # the long-reply check only ever sees this turn's words
            guard.turn_over()
        if event.turn_complete and guard.hang_up_now():
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
