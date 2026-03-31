# Voice Agent — System Architecture

## Overview

Voice Agent is a **real-time AI voice agent** for clinical appointment management. A patient receives an outbound phone call, speaks naturally (in English, Hindi, or Tamil), and the AI agent books, cancels, or reschedules appointments on their behalf — with zero human involvement.
v
---

## High-Level Architecture

```
Patient Phone
     │
     │  Twilio call (public PSTN)
     ▼
┌─────────────┐      POST /api/twilio/voice       ┌─────────────────────────┐
│   Twilio    │ ─────────────────────────────────▶ │   FastAPI Backend        │
│  (PSTN/SIP) │ ◀──────── TwiML response ────────  │   (Uvicorn · Port 8001)  │
└─────────────┘                                    └────────────┬────────────┘
     │                                                          │
     │  WebSocket media stream (mu-law 8kHz)                    │
     └──────────────────────────────────────────▶ /ws/call     │
                                                               │
                              ┌────────────────────────────────▼──────────────────────────────┐
                              │                    VOICE PIPELINE                               │
                              │  VAD  ─▶  STT (Deepgram)  ─▶  LLM Agent  ─▶  TTS (Edge TTS)  │
                              └────────────────────────────────────────────────────────────────┘
                                                               │
                                              ┌────────────────┼────────────────┐
                                              ▼                ▼                ▼
                                         PostgreSQL         Redis          LangSmith
                                         (NeonDB)         (Upstash)       (Tracing)
                                     Patients/Doctors/
                                       Slots/Bookings     Session Mem
```

---

## Directory Structure

```
Voice Agent/
├── backend/
│   ├── main.py              # FastAPI app entry point + CORS + lifespan
│   ├── config.py            # Pydantic Settings (env vars, extra=allow)
│   ├── models.py            # SQLAlchemy ORM models
│   ├── database.py          # Async engine, session factory, seeder
│   ├── api/
│   │   ├── routes.py        # REST endpoints (health, doctors, slots, bookings, call)
│   │   └── websocket.py     # Twilio Media Streams WebSocket handler
│   ├── voice/
│   │   ├── vad.py           # WebRTC Voice Activity Detection
│   │   ├── stt.py           # Deepgram speech-to-text
│   │   ├── tts.py           # Edge TTS (Microsoft neural voices → mu-law 8kHz)
│   │   └── pipeline.py      # Orchestrates VAD→STT→LLM→TTS per turn
│   ├── agent/
│   │   ├── graph.py         # LangGraph agent (Gemini LLM + tool nodes)
│   │   └── tools.py         # LangChain tools: check_availability, book, cancel, reschedule
│   ├── memory/
│   │   ├── redis_client.py  # Sync Redis client (Upstash)
│   │   ├── session.py       # Async Redis: per-call session memory (turns, language, patient)
│   │   └── longterm.py      # PostgreSQL: patient history + system prompt builder
│   ├── scheduling/
│   │   └── slots.py         # Slot availability, booking, cancellation, reschedule logic
│   └── campaigns/
│       └── outbound.py      # Twilio REST: initiate outbound calls
└── frontend/
    ├── src/
    │   └── App.tsx          # React Mission Control HUD
    └── vite.config.ts       # Dev server + /api proxy → localhost:8001
```

---

## Component Deep-Dives

### 1. Call Lifecycle

1. **Frontend** → `POST /api/call?to=+91XXXXXXXXXX`
2. **`campaigns/outbound.py`** calls `Twilio REST API` with webhook `POST /api/twilio/voice`
3. Twilio calls the patient phone
4. When answered, Twilio POSTs `/api/twilio/voice` → backend returns **TwiML** pointing to `wss://<ngrok>/ws/call`
5. Twilio opens a **WebSocket** and streams raw **mu-law 8kHz** audio

### 2. WebSocket Handler (`api/websocket.py`)

- Accepts Twilio `start`, `media`, `stop` events
- On `start`: resolves patient from caller phone (Redis + DB), sends greeting via TTS
- On `media`: feeds mu-law bytes into **VAD**
- VAD accumulates audio until speech ends, then pushes PCM to the **speech queue**
- An async background `_speech_processor` task processes each turn through the **Voice Pipeline**
- Supports **barge-in**: a new utterance cancels the in-flight TTS task

### 3. Voice Pipeline (`voice/pipeline.py`)

Each turn:
```
PCM  →  Deepgram STT  →  LangGraph Agent  →  Edge TTS  →  mu-law chunks  →  Twilio WebSocket
```
- Measures and logs latency per stage: `stt_ms`, `llm_ms`, `tts_first_chunk_ms`, `total_ms`
- Logs to `/app/latency_logs.jsonl` (read by `/api/latency` endpoint → React HUD)

### 4. AI Agent (`agent/graph.py` + `agent/tools.py`)

- **Model:** Google Gemini 2.5 Flash via `langchain-google-genai`
- **Framework:** LangGraph `StateGraph` with conditional edges (tool call → continue or end)
- **Tools (6):**
  | Tool | Action |
  |------|--------|
  | `check_availability` | Query DB for open slots by doctor/specialty/date |
  | `book_appointment` | Book a slot for the identified patient |
  | `cancel_appointment` | Cancel an existing booking |
  | `reschedule_appointment` | Move a booking to a new slot |
  | `get_patient_context` | Fetch patient name, history from DB |
  | `detect_and_set_language` | Auto-detect Hindi/Tamil/English, persist preference |

### 5. Memory Layers

| Layer | Store | Contents |
|-------|-------|----------|
| **Short-term (session)** | Redis (Upstash) | Last 10 conversation turns, detected language, patient ID |
| **Long-term** | PostgreSQL (NeonDB) | Patients, Doctors, Slots, Appointments, CampaignLogs |

### 6. Text-to-Speech (`voice/tts.py`)

- Uses **`edge-tts`** (Microsoft Edge neural voices, free, no API key)
- Voice selection by language:
  - English → `en-US-AriaNeural`
  - Hindi → `hi-IN-MadhurNeural`
  - Tamil → `ta-IN-PallaviNeural`
- Decodes MP3 stream via **`audioread`** (Mac CoreAudio), resamples 24kHz→8kHz, encodes to **mu-law** for Twilio

### 7. Frontend React HUD (`frontend/src/App.tsx`)

- **Call Me button:** `POST /api/call?to=<number>` via Vite proxy
- **Latency monitor:** polls `GET /api/latency` every 1s, renders bar graph
- **Bookings table:** polls `GET /api/appointments` every 5s (live sync)
- **Live transcript panel:** displays conversation log with speaker labels
- Vite proxy forwards `/api/*` → `http://localhost:8001`

---

## External Services

| Service | Purpose | Credentials |
|---------|---------|------------|
| **Twilio** | PSTN calls + Media Streams WebSocket | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` |
| **Deepgram** | Speech-to-Text (STT) | `DEEPGRAM_API_KEY` |
| **edge-tts** | Text-to-Speech — free, no key needed | — |
| **Google Gemini** | LLM reasoning + tool calling | `GOOGLE_API_KEY` |
| **NeonDB** | PostgreSQL (patients, appointments) | `DATABASE_URL` |
| **Upstash Redis** | Session memory (TLS) | `REDIS_URL` |
| **ngrok** | Expose local backend to Twilio webhooks | Auth token in `~/.ngrok2/ngrok.yml` |
| **LangSmith** | LLM trace observability | `LANGCHAIN_API_KEY` |

---

## Data Models

```
Patient ─┬─ Appointments ─── Slot ─── Doctor
         └─ CampaignLogs
```

- **Patient:** name, phone (unique), language preference
- **Doctor:** name, specialty, availability flag
- **Slot:** doctor, start/end time, is_booked
- **Appointment:** patient, slot, status (scheduled/cancelled/rescheduled/completed), notes
- **CampaignLog:** patient, campaign_type, outcome, Twilio call_sid

---

## Local Development

```bash
# 1. Start everything
./start_all.sh

# Services:
# Backend  → http://localhost:8001
# Frontend → http://localhost:5173
# Ngrok    → https://melaine-homochronous-cristian.ngrok-free.dev

# 2. Trigger a call
curl -X POST "http://localhost:8001/api/call?to=+91XXXXXXXXXX"

# 3. Monitor logs
tail -f backend/uvicorn.log
```

---

## Environment Variables (backend/.env)

```env
DATABASE_URL=postgresql://...
REDIS_URL=rediss://...
GOOGLE_API_KEY=...
DEEPGRAM_API_KEY=...
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=<32-char hex>
TWILIO_PHONE_NUMBER=+1...
API_BASE_URL=https://<ngrok-domain>
WS_BASE_URL=wss://<ngrok-domain>
LANGCHAIN_API_KEY=...
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=voice-agent
```
