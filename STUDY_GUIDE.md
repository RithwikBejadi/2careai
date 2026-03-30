# Voice AI Agent - Complete Study Guide

**Purpose**: Fully understand YOUR codebase so you can explain ANY file in 30 seconds.

---

## 1. THE BIG PICTURE (Memorize This First)

```
Phone Call → Twilio → WebSocket → VAD → STT → LLM Agent → TTS → Audio Back
                                   ↓
                              PostgreSQL (slots, appointments)
                              Redis (session state)
```

### One-Sentence Summary
A voice AI agent that helps patients book/cancel/reschedule clinical appointments in 3 languages (English, Hindi, Tamil) using Twilio for telephony, Deepgram for speech-to-text, LangGraph for AI reasoning, and Edge-TTS for text-to-speech.

---

## 2. FILE-BY-FILE BREAKDOWN

### Entry Point: `backend/main.py`
**Purpose**: Starts the FastAPI server and initializes the database.

**Key Concepts**:
- `lifespan` context manager: Runs `init_db()` on startup, creates tables + seeds demo data
- Two routers mounted:
  - `/api/*` - REST endpoints (routes.py)
  - `/ws/*` - WebSocket for voice calls (websocket.py)
- CORS middleware allows cross-origin requests

**If asked "How does the app start?"**:
> "FastAPI uses a lifespan context manager. On startup, it calls init_db() which creates database tables using SQLAlchemy's create_all and seeds demo doctors/patients/slots. Then it mounts REST routes on /api and WebSocket routes on /ws."

---

### Configuration: `backend/config.py`
**Purpose**: Load all environment variables using Pydantic Settings.

**Key Variables**:
- `DATABASE_URL` - PostgreSQL connection (Neon.tech)
- `REDIS_URL` - Redis connection (Upstash)
- `DEEPGRAM_API_KEY` - Speech-to-text service
- `ELEVENLABS_API_KEY` - Text-to-speech (though we use Edge-TTS now)
- `TWILIO_*` - Phone call credentials
- `VOICE_EN/HI/TA` - Voice IDs for different languages

**If asked "How do you manage configuration?"**:
> "I use Pydantic's BaseSettings which automatically loads from .env file. All API keys and database URLs are environment variables for security - never hardcoded."

---

### Database Models: `backend/models.py`
**Purpose**: Define the 5 database tables using SQLAlchemy ORM.

**Tables**:
1. **Patient** - id, name, phone (unique+indexed), language_preference (en/hi/ta)
2. **Doctor** - id, name, specialty, is_available
3. **Slot** - id, doctor_id (FK), start_time, end_time, is_booked
4. **Appointment** - id, patient_id (FK), slot_id (FK), status, notes
5. **CampaignLog** - tracks outbound reminder calls

**Key Design Decisions**:
- Integer primary keys (not UUID) for simplicity
- `to_dict()` method on each model for JSON serialization
- `selectin` lazy loading for relationships (prevents N+1 queries)
- Enums for Language and AppointmentStatus

**If asked "Explain your database schema"**:
> "Five tables: Patient stores contact info and language preference. Doctor has specialty and availability. Slot belongs to a doctor with start/end times and booking status. Appointment links a patient to a slot with a status enum (scheduled/cancelled/rescheduled/completed). CampaignLog tracks outbound reminder calls. I use integer PKs and selectin loading to prevent N+1 queries."

---

### Database Connection: `backend/database.py`
**Purpose**: Create async database engine and session factory, plus seed demo data.

**Key Code Explained**:
```python
def _make_asyncpg_url(url: str) -> str:
    # Neon.tech uses ?sslmode=require but asyncpg needs connect_args instead
    # So we strip sslmode and channel_binding from URL
    # Then create SSL context separately
```

**Seeder Class**:
- Seeds 4 doctors (3 available, 1 unavailable)
- Seeds 3 patients with different language preferences
- Seeds 63 slots (3 doctors × 3 slots/day × 7 days)

**If asked "How do you handle database connections?"**:
> "I use SQLAlchemy's async engine with asyncpg driver. For Neon.tech's SSL requirement, I strip sslmode from the URL and pass an SSL context via connect_args. I use async_sessionmaker with expire_on_commit=False so objects stay usable after commit. The seeder runs on startup and only seeds if tables are empty."

---

### Slot Service: `backend/scheduling/slots.py`
**Purpose**: Core booking logic with conflict prevention.

**This is THE most important file for interviews!**

**Key Methods**:
1. `get_available_slots()` - Query available slots with filters
2. `book_appointment()` - Book with 4 conflict checks
3. `cancel_appointment()` - Cancel and free the slot
4. `reschedule_appointment()` - Cancel old, book new

**The 4 Conflict Checks** (MEMORIZE THESE):
```python
# 1. Slot not found
if slot is None:
    raise ConflictError("Slot not found.", alternatives=[])

# 2. Slot already passed (time check)
if slot_start <= now:
    raise ConflictError("That slot has already passed.", alternatives=alts)

# 3. Doctor unavailable
if slot.doctor and not slot.doctor.is_available:
    raise ConflictError(f"Dr. {slot.doctor.name} is not accepting appointments.")

# 4. Slot already booked (race condition protection)
if slot.is_booked:
    raise ConflictError("That slot is already taken.", alternatives=alts)

# 5. Patient overlap (double-booking themselves)
# Check if patient has existing appointment at same time
```

**Race Condition Prevention**:
```python
.with_for_update()  # SELECT FOR UPDATE - locks the row
```

**If asked "How do you prevent double-booking?"**:
> "I use PostgreSQL's SELECT FOR UPDATE to lock the slot row during the booking transaction. This prevents race conditions where two requests try to book the same slot simultaneously. I also check 4 conflict cases: slot existence, time validation (not in past), doctor availability, and slot not already booked. Additionally, I check for patient overlap - if they already have an appointment at that time."

**If asked "What happens when a conflict occurs?"**:
> "I raise a custom ConflictError exception with a reason message and a list of alternative slots. The alternatives are fetched using helper methods like _next_available() for same doctor, or _same_specialty_slots() for other doctors with same specialty."

---

### Agent Tools: `backend/agent/tools.py`
**Purpose**: Define LangChain tools that the AI agent can call.

**Context Variables** (IMPORTANT CONCEPT):
```python
_db_ctx: contextvars.ContextVar[Optional[AsyncSession]]
_session_id_ctx: contextvars.ContextVar[str]
_patient_id_ctx: contextvars.ContextVar[Optional[int]]

def set_tool_context(db, session_id, patient_id):
    # MUST be called before each agent.ainvoke()
```

**Why contextvars?**
> "LangGraph tools are stateless functions. But we need database access and patient context. Context variables let us pass this per-request without polluting function signatures. Each async task gets its own context."

**The 6 Tools**:
1. `check_availability` - Query open slots by doctor/specialty/date
2. `book_appointment` - Book using slot_id
3. `cancel_appointment` - Cancel by appointment_id
4. `reschedule_appointment` - Cancel + book in one operation
5. `get_patient_context` - Fetch patient profile + history
6. `detect_and_set_language` - Auto-detect Hindi/Tamil/English from Unicode

**Language Detection Logic**:
```python
def _detect_language(text: str) -> str:
    for ch in text:
        cp = ord(ch)
        if 0x0B80 <= cp <= 0x0BFF:  # Tamil Unicode block
            return "ta"
        if 0x0900 <= cp <= 0x097F:  # Devanagari Unicode block
            return "hi"
    return "en"  # Default English
```

**If asked "How does language detection work?"**:
> "I scan the text character by character and check Unicode code points. Tamil characters fall in the 0x0B80-0x0BFF range, Hindi/Devanagari in 0x0900-0x097F. If neither is found, I default to English. This is more reliable than ML-based detection for our specific use case."

---

### LangGraph Agent: `backend/agent/graph.py`
**Purpose**: Build the AI reasoning graph using LangGraph.

**Architecture**:
```
[agent node] --has tool calls?--> [tools node] ---> [agent node]
     |                                                    |
     +------ no tool calls -----> END                     |
     +<---------------------------------------------------+
```

**State Definition**:
```python
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    system_prompt: str
```

**The Graph**:
```python
_workflow = StateGraph(AgentState)
_workflow.add_node('agent', _agent_node)
_workflow.add_node('tools', _tools_node)
_workflow.set_entry_point('agent')
_workflow.add_conditional_edges('agent', _should_continue, {'tools': 'tools', 'end': END})
_workflow.add_edge('tools', 'agent')
agent = _workflow.compile()
```

**If asked "How does the AI agent work?"**:
> "I use LangGraph's StateGraph pattern. The agent node calls Gemini with tools bound. If the LLM response has tool_calls, we route to the tools node which executes them, then back to agent. If no tool calls, we go to END. This loop continues until the LLM decides it has a final answer."

---

### Voice Activity Detection: `backend/voice/vad.py`
**Purpose**: Detect when the user stops speaking.

**How VAD Works**:
```
Twilio sends mulaw audio chunks
    → Convert to PCM (audioop.ulaw2lin)
    → Buffer into 20ms frames
    → webrtcvad checks each frame: speech or silence?
    → Track consecutive silence frames
    → After 25 silence frames (500ms) + min 10 speech frames
    → Fire on_speech_end callback with accumulated PCM
```

**Key Parameters**:
- `aggressiveness=2` (0-3, higher = more aggressive at filtering non-speech)
- `FRAME_MS = 20` (webrtcvad requires specific frame sizes)
- `SILENCE_FRAMES_THRESHOLD = 25` (25 × 20ms = 500ms silence triggers end)
- `MIN_SPEECH_FRAMES = 10` (must have at least 200ms of speech)

**If asked "How do you detect when the user stops speaking?"**:
> "I use webrtcvad, Google's voice activity detection library. Twilio sends mulaw audio which I convert to PCM. I buffer into 20ms frames because webrtcvad only accepts specific frame sizes. Each frame is classified as speech or silence. After 500ms of consecutive silence following at least 200ms of speech, I fire the on_speech_end callback with the accumulated audio buffer."

---

### Speech-to-Text: `backend/voice/stt.py`
**Purpose**: Convert audio to text using Deepgram.

**Key Code**:
```python
options = PrerecordedOptions(
    model="nova-2",       # Deepgram's best model
    language="multi",     # Auto-detect language
    smart_format=True,    # Add punctuation
    encoding="linear16",  # PCM format
    sample_rate=8000,     # Twilio's rate
    channels=1,           # Mono audio
)
```

**If asked "How does speech-to-text work?"**:
> "I use Deepgram's Nova-2 model with async prerecorded API. The audio comes as PCM bytes at 8kHz mono (Twilio's format). I set language to 'multi' for automatic language detection since we support 3 languages. Deepgram returns a transcript which I extract from the response."

---

### Text-to-Speech: `backend/voice/tts.py`
**Purpose**: Convert AI response to speech.

**Implementation**: Uses Edge-TTS (Microsoft's free TTS) instead of ElevenLabs to save costs.

**Voice Mapping**:
```python
_VOICE_MAP = {
    'en': "en-US-AriaNeural",
    'hi': "hi-IN-MadhurNeural",
    'ta': "ta-IN-PallaviNeural"
}
```

**Process**:
```
Text → Edge-TTS → MP3 chunks → Decode to PCM → Resample to 8kHz → Convert to mulaw → Stream chunks
```

**If asked "Why Edge-TTS instead of ElevenLabs?"**:
> "ElevenLabs charges per character and has usage limits. Edge-TTS uses Microsoft's neural voices for free with similar quality. I stream the MP3, decode to PCM, resample from native sample rate to 8kHz (Twilio's rate), then convert to mulaw which Twilio expects. I yield chunks to enable streaming."

---

### WebSocket Handler: `backend/api/websocket.py`
**Purpose**: Handle real-time Twilio Media Streams.

**This is THE main orchestration file!**

**Flow**:
```
1. Connection opens → accept WebSocket
2. Twilio sends "start" event → extract caller phone, send greeting TTS
3. Twilio sends "media" events → pass mulaw to VAD
4. VAD fires on_speech_end → queue PCM for processing
5. _process_speech: STT → Agent → TTS → send back to Twilio
6. "stop" event or disconnect → cleanup
```

**Barge-in Handling** (interrupting the AI):
```python
# If new speech detected while TTS is playing:
if active_tts_task and not active_tts_task.done():
    interrupt_event.set()
    active_tts_task.cancel()
    await _clear_audio(websocket, stream_sid)  # Tell Twilio to stop playing
```

**Session Memory Integration**:
- Get patient ID from phone number
- Store language preference
- Track conversation turns

**If asked "How does the WebSocket handler work?"**:
> "Twilio opens a WebSocket and sends events. On 'start', I extract the caller's phone, look up their patient record to get language preference, and stream a greeting. On 'media' events, I pass audio chunks to the VAD. When VAD detects speech end, it queues the audio. A background task processes the queue: STT to get text, run through LangGraph agent for response, TTS to generate audio, then stream back to Twilio."

**If asked "How do you handle barge-in?"**:
> "If the user starts speaking while the AI is still playing audio, I need to interrupt. I maintain an interrupt_event asyncio.Event. When new speech comes in, I set the event, cancel the active TTS task, and send a 'clear' event to Twilio which tells it to flush its audio buffer."

---

### Session Memory: `backend/memory/session.py`
**Purpose**: Store conversation state in Redis.

**What's Stored**:
- `turns` - List of conversation messages (max 10)
- `language` - Detected language preference
- `patient_id` - Linked patient
- `pending` - Awaiting confirmation state
- `agent_state` - LangGraph state

**Key Design**:
```python
_SESSION_TTL = 60 * 30  # 30 minutes
_MAX_TURNS = 10

# All keys prefixed with session:{session_id}:{field}
```

**Pipeline for Efficiency**:
```python
pipe = client.pipeline()
pipe.rpush(k, turn)         # Add turn
pipe.ltrim(k, -_MAX_TURNS, -1)  # Keep only last 10
pipe.expire(k, _SESSION_TTL)    # Refresh TTL
await pipe.execute()        # Single round-trip
```

**If asked "How do you manage session state?"**:
> "I use Redis for ephemeral session data with 30-minute TTL. Each session has multiple keys: turns for conversation history (capped at 10 for context window), language preference, patient_id, and pending confirmations. I use pipelining to batch Redis commands into single round-trips for efficiency."

---

### Long-term Memory: `backend/memory/longterm.py`
**Purpose**: Fetch patient history from PostgreSQL and build system prompts.

**get_patient_context()**:
- Fetches patient profile
- Gets last 3 appointments (scheduled or completed)

**build_system_prompt()**:
- Starts with role prompt (professional AI receptionist rules)
- Adds patient profile if known
- Injects last 6 conversation turns for context continuity

**If asked "How do you personalize responses?"**:
> "I query PostgreSQL for patient history - their profile and last 3 appointments. This goes into the system prompt so the LLM knows the caller's context. I also inject the last 6 conversation turns from Redis session memory so the agent remembers what was just discussed."

---

### REST Routes: `backend/api/routes.py`
**Purpose**: HTTP endpoints for testing and dashboard.

**Key Endpoints**:
- `GET /api/health` - Health check
- `GET /api/doctors` - List doctors
- `GET /api/slots` - List available slots
- `GET /api/patients` - List patients
- `GET /api/appointments` - List appointments
- `POST /api/twilio/voice` - Return TwiML connecting to WebSocket
- `POST /api/call?to=+91...` - Trigger outbound call
- `GET /api/transcript` - Get live call transcript

---

## 3. KEY ARCHITECTURE DECISIONS

### Why these tech choices?

| Tech | Reason |
|------|--------|
| FastAPI | Async-native, great for WebSocket + DB |
| SQLAlchemy 2.0 async | Type-safe ORM with async support |
| PostgreSQL (Neon) | ACID transactions, SELECT FOR UPDATE |
| Redis (Upstash) | Fast ephemeral session storage |
| LangGraph | Structured agent with tool loops |
| Deepgram | Best multilingual STT accuracy |
| Edge-TTS | Free, high-quality neural voices |
| webrtcvad | Battle-tested VAD from Google |

### Why async everywhere?
> "Voice calls are I/O bound - waiting on network, database, external APIs. Async allows handling multiple concurrent calls without blocking. A single process can handle many WebSocket connections because we're never CPU-bound."

### Why SELECT FOR UPDATE?
> "Two users could try booking the same slot simultaneously. Without locking, both would read is_booked=False and both would succeed. SELECT FOR UPDATE locks the row until our transaction commits, ensuring only one succeeds."

### Why contextvars in tools?
> "LangChain tools are defined as plain functions, but they need database sessions and patient context which are per-request. Contextvars provide thread-local storage that works with asyncio, letting us pass context without changing tool signatures."

---

## 4. COMMON INTERVIEW QUESTIONS

### "Walk me through a booking flow"
1. User says "I want to book an appointment"
2. VAD detects speech end, sends PCM to STT
3. Deepgram returns transcript
4. LangGraph agent decides to call `check_availability` tool
5. Tool queries PostgreSQL for available slots
6. Agent responds asking which slot
7. User says "Slot 5"
8. Agent calls `book_appointment(slot_id=5)`
9. Tool acquires row lock, checks conflicts, creates Appointment, marks slot booked
10. Agent confirms booking
11. TTS speaks confirmation, streamed to Twilio

### "What happens if two people book the same slot?"
> "First request acquires row lock via SELECT FOR UPDATE. Second request blocks until first commits. After first commits, second sees is_booked=True and gets a ConflictError with alternative slots."

### "How do you scale this?"
> "Currently single-process. To scale: multiple Uvicorn workers behind a load balancer, Redis handles session state, PostgreSQL handles coordination via row locks. For more scale: Kubernetes pods, connection pooling (PgBouncer), Redis cluster."

### "What's the latency like?"
> "Currently around 1000ms end-to-end. Breakdown: VAD wait (500ms), STT (~200ms), LLM (~300ms), TTS (~200ms). Could improve with streaming STT, smaller LLM, or precomputed TTS for common phrases."

### "What breaks? Edge cases?"
> "Lost WebSocket connection mid-booking - transaction rolls back, no orphan state. Redis down - sessions fail gracefully, stateless fallback. LLM hallucination - tool validation catches invalid slot_ids. Long audio - VAD buffers indefinitely until speech ends."

---

## 5. CODE SNIPPETS TO MEMORIZE

### The booking conflict check (slots.py:87-154)
```python
async def book_appointment(self, db, *, slot_id, patient_id, notes=None):
    # 1. Lock the slot row
    result = await db.execute(
        select(Slot).where(Slot.id == slot_id)
        .options(selectinload(Slot.doctor))
        .with_for_update()  # <-- This prevents race conditions
    )
    slot = result.scalar_one_or_none()

    # 2. Validate slot exists
    if slot is None:
        raise ConflictError("Slot not found.", alternatives=[])

    # 3. Check time (not in past)
    if slot_start <= now:
        raise ConflictError("Slot has passed.", alternatives=await self._next_available(...))

    # 4. Check doctor available
    if not slot.doctor.is_available:
        raise ConflictError("Doctor unavailable.", alternatives=await self._same_specialty_slots(...))

    # 5. Check not already booked
    if slot.is_booked:
        raise ConflictError("Already taken.", alternatives=await self._nearest_open_slots(...))

    # 6. Check patient doesn't have overlapping appointment
    # Query for same patient, same time range

    # 7. Book it
    slot.is_booked = True
    appointment = Appointment(patient_id=patient_id, slot_id=slot_id, ...)
    db.add(appointment)
    await db.commit()
```

### VAD core loop (vad.py:34-62)
```python
def process_chunk(self, mulaw_data: bytes) -> bool:
    pcm_data = audioop.ulaw2lin(mulaw_data, 2)  # Convert mulaw to PCM
    self._pcm_buffer += pcm_data

    while len(self._pcm_buffer) >= FRAME_BYTES_PCM:  # 320 bytes = 20ms
        frame = self._pcm_buffer[:FRAME_BYTES_PCM]
        self._pcm_buffer = self._pcm_buffer[FRAME_BYTES_PCM:]

        is_speech = self._vad.is_speech(frame, SAMPLE_RATE)
        if is_speech:
            self._speech_frames += 1
            self._silence_frames = 0
            self._speech_buffer += frame
        elif self._is_speaking:
            self._silence_frames += 1
            if self._silence_frames >= 25 and self._speech_frames >= 10:
                # Speech ended! Fire callback
                self._on_speech_end(self._speech_buffer)
```

### Agent graph (graph.py)
```python
def _should_continue(state):
    last = state['messages'][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return 'tools'  # LLM wants to call a tool
    return 'end'  # LLM is done

# Graph: agent -> (tools?) -> agent -> ... -> end
_workflow = StateGraph(AgentState)
_workflow.add_node('agent', _agent_node)
_workflow.add_node('tools', _tools_node)
_workflow.set_entry_point('agent')
_workflow.add_conditional_edges('agent', _should_continue,
    {'tools': 'tools', 'end': END})
_workflow.add_edge('tools', 'agent')
agent = _workflow.compile()
```

---

## 6. PRACTICE PLAN

### Day 1 (6 hours)
- [ ] Read this guide completely
- [ ] Open each file, match it to this guide
- [ ] Draw the architecture diagram from memory
- [ ] Explain the booking flow out loud

### Day 1 (next 6 hours)
- [ ] Write `book_appointment` from memory
- [ ] Write the VAD `process_chunk` from memory
- [ ] Explain conflict checks without looking

### Day 2 (12 hours)
- [ ] Random file opening: explain in 30 seconds
- [ ] Answer all interview questions out loud
- [ ] Have a friend ask random questions
- [ ] Practice until zero hesitation

---

## 7. QUICK REFERENCE CARD

```
┌─────────────────────────────────────────────────────────────┐
│ FILE → WHAT IT DOES                                          │
├─────────────────────────────────────────────────────────────┤
│ main.py       → Entry point, mounts routers, lifespan       │
│ config.py     → Environment variables via Pydantic          │
│ models.py     → 5 SQLAlchemy tables (Patient/Doctor/Slot...)│
│ database.py   → Async engine, session factory, seeder       │
│ slots.py      → Booking logic, 4 conflict checks, row locks │
│ tools.py      → 6 LangChain tools, contextvars for context  │
│ graph.py      → LangGraph StateGraph, agent→tools loop      │
│ websocket.py  → Twilio handler, VAD→STT→Agent→TTS pipeline  │
│ vad.py        → webrtcvad, detects speech end (500ms silence)│
│ stt.py        → Deepgram Nova-2, multilingual               │
│ tts.py        → Edge-TTS, MP3→PCM→mulaw conversion          │
│ session.py    → Redis session state, 30min TTL              │
│ longterm.py   → Patient history from Postgres, system prompt│
│ routes.py     → REST API endpoints, TwiML generation        │
└─────────────────────────────────────────────────────────────┘
```

---

**Remember**: You BUILT this. The AI helped speed up coding, but you made the architecture decisions. You understand why each piece exists. That's what matters.

Go crush it.
