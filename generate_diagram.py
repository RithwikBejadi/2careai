"""Run: python generate_diagram.py  →  architecture.png"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

fig, ax = plt.subplots(figsize=(18, 12))
ax.set_xlim(0, 18)
ax.set_ylim(0, 12)
ax.axis("off")
fig.patch.set_facecolor("#0f172a")
ax.set_facecolor("#0f172a")

C_BLUE   = "#38bdf8"
C_PURPLE = "#a78bfa"
C_GREEN  = "#34d399"
C_ORANGE = "#fb923c"
C_PINK   = "#f472b6"
C_GRAY   = "#94a3b8"
C_BG     = "#1e293b"
C_TEXT   = "#f1f5f9"
C_DIM    = "#64748b"

def box(ax, x, y, w, h, label, sublabel="", color=C_BLUE, fontsize=9):
    rect = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.08",
        linewidth=1.5,
        edgecolor=color,
        facecolor=C_BG,
        zorder=3,
    )
    ax.add_patch(rect)
    cy = y + h / 2
    if sublabel:
        ax.text(x + w/2, cy + 0.13, label,  ha="center", va="center",
                color=color,  fontsize=fontsize, fontweight="bold", zorder=4)
        ax.text(x + w/2, cy - 0.17, sublabel, ha="center", va="center",
                color=C_GRAY, fontsize=7, zorder=4)
    else:
        ax.text(x + w/2, cy, label, ha="center", va="center",
                color=color, fontsize=fontsize, fontweight="bold", zorder=4)

def arrow(ax, x1, y1, x2, y2, label="", color=C_DIM):
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(arrowstyle="-|>", color=color, lw=1.4),
        zorder=2,
    )
    if label:
        mx, my = (x1+x2)/2, (y1+y2)/2
        ax.text(mx+0.05, my+0.07, label, ha="left", va="bottom",
                color=C_GRAY, fontsize=6.5, zorder=5)

def section_bg(ax, x, y, w, h, color, alpha=0.06):
    rect = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.1",
        linewidth=0.8,
        edgecolor=color,
        facecolor=color,
        alpha=alpha,
        zorder=1,
    )
    ax.add_patch(rect)

# ── title ───────────────────────────────────────────────────────────────────
ax.text(9, 11.5, "Voice Agent — Real-Time Multilingual Voice AI Architecture",
        ha="center", va="center", color=C_TEXT, fontsize=14, fontweight="bold")

# ── INBOUND CALL FLOW (left column, top-to-bottom) ──────────────────────────
section_bg(ax, 0.3, 3.0, 3.8, 8.3, C_BLUE)
ax.text(2.2, 11.1, "TELEPHONY", ha="center", color=C_BLUE, fontsize=7.5,
        fontweight="bold", alpha=0.8)

box(ax, 0.6, 9.8, 3.2, 0.8, "Caller (India)",   "Twilio PSTN / SIP",   C_BLUE)
box(ax, 0.6, 8.6, 3.2, 0.8, "Twilio",            "Media Streams WS",    C_BLUE)
box(ax, 0.6, 7.4, 3.2, 0.8, "VAD",               "webrtcvad  8 kHz",    C_BLUE)
box(ax, 0.6, 6.2, 3.2, 0.8, "Deepgram STT",      "Nova-2  multi-lang",  C_BLUE)
box(ax, 0.6, 5.0, 3.2, 0.8, "ElevenLabs TTS",    "ulaw_8000 stream",    C_BLUE)
box(ax, 0.6, 3.8, 3.2, 0.8, "Twilio ← audio",    "base64 mulaw out",    C_BLUE)

arrow(ax, 2.2, 9.8, 2.2, 9.4,  "PSTN")
arrow(ax, 2.2, 8.6, 2.2, 8.2,  "mulaw 8 kHz chunks")
arrow(ax, 2.2, 7.4, 2.2, 7.0,  "PCM → on_speech_end")
arrow(ax, 2.2, 6.2, 2.2, 5.8,  "transcript")
arrow(ax, 2.2, 5.0, 2.2, 4.6,  "mulaw bytes")

# ── AGENT CORE (centre) ─────────────────────────────────────────────────────
section_bg(ax, 4.5, 4.5, 9.0, 5.0, C_PURPLE)
ax.text(9.0, 9.3, "AGENT CORE", ha="center", color=C_PURPLE,
        fontsize=7.5, fontweight="bold", alpha=0.8)

box(ax, 5.5, 7.6, 7.0, 1.4,
    "LangGraph StateGraph",
    "Groq llama-3.3-70b-versatile  |  tool_calls → ToolNode  |  streaming",
    C_PURPLE, fontsize=9)

# tools row
box(ax, 4.7,  5.8, 2.0, 0.9, "check_availability",  "slots query",       C_PINK, 7.5)
box(ax, 6.85, 5.8, 2.0, 0.9, "book_appointment",    "SELECT FOR UPDATE",  C_PINK, 7.5)
box(ax, 9.0,  5.8, 2.0, 0.9, "cancel / reschedule", "atomic swap",        C_PINK, 7.5)
box(ax, 11.15,5.8, 2.0, 0.9, "get_patient_context", "Postgres fetch",     C_PINK, 7.5)

for tx in [5.7, 7.85, 10.0, 12.15]:
    arrow(ax, tx, 7.6, tx, 6.7, color=C_PURPLE)

# pipeline connections
arrow(ax, 4.0, 6.6, 5.5, 7.8, "text", C_BLUE)       # STT → agent
arrow(ax, 5.5, 7.6, 4.0, 5.3, "sentence stream", C_BLUE)  # agent → TTS

# ── VOICE PIPELINE box ──────────────────────────────────────────────────────
box(ax, 4.7, 4.5, 8.6, 1.0,
    "VoicePipeline.handle_turn()",
    "async generator  |  sentence buffer  [.!?]  |  latency -> /app/latency_logs.jsonl",
    C_GREEN, 8)

arrow(ax, 9.0, 7.6, 9.0, 5.5, color=C_PURPLE)

# ── MEMORY layer ────────────────────────────────────────────────────────────
section_bg(ax, 0.3, 0.3, 7.8, 3.0, C_GREEN)
ax.text(4.2, 3.1, "MEMORY", ha="center", color=C_GREEN,
        fontsize=7.5, fontweight="bold", alpha=0.8)

box(ax, 0.6, 1.6, 3.5, 1.2,
    "Redis  (Upstash)",
    "session:{id}:turns  language  pending\npatient_id  agent_state   TTL=30 min",
    C_GREEN, 8)
box(ax, 4.4, 1.6, 3.5, 1.2,
    "PostgreSQL  (Neon)",
    "Patient  Doctor  Slot\nAppointment  CampaignLog",
    C_GREEN, 8)

box(ax, 0.6, 0.4, 3.5, 0.8, "LangSmith Tracing", "full chain trace / turn", C_GREEN, 7.5)
box(ax, 4.4, 0.4, 3.5, 0.8, "Latency API", "GET /api/latency (last 20)", C_GREEN, 7.5)

# memory ↔ agent arrows
arrow(ax, 2.35, 2.8, 7.5,  8.0, "system prompt",   C_GREEN)
arrow(ax, 6.1,  2.8, 7.8,  7.8, "patient context",  C_GREEN)

# ── OUTBOUND / CAMPAIGNS ────────────────────────────────────────────────────
section_bg(ax, 8.5, 0.3, 9.2, 3.0, C_ORANGE)
ax.text(13.1, 3.1, "CAMPAIGNS & OUTBOUND", ha="center", color=C_ORANGE,
        fontsize=7.5, fontweight="bold", alpha=0.8)

box(ax, 8.8,  1.6, 3.0, 1.2, "Celery Beat",        "hourly schedule_reminders",  C_ORANGE, 8)
box(ax, 12.1, 1.6, 3.0, 1.2, "Celery Worker",      "send_reminder tasks",         C_ORANGE, 8)
box(ax, 15.1, 1.6, 2.5, 1.2, "Twilio REST",        "calls.create() outbound",     C_ORANGE, 8)

box(ax, 8.8,  0.4, 3.0, 0.8, "Redis Broker",       "rediss:// Upstash",           C_ORANGE, 8)
box(ax, 12.1, 0.4, 3.0, 0.8, "CampaignLog",        "outcome → Postgres",          C_ORANGE, 8)
box(ax, 15.1, 0.4, 2.5, 0.8, "Docker worker",      "separate container",          C_ORANGE, 8)

arrow(ax, 11.8, 2.2, 12.1, 2.2, color=C_ORANGE)
arrow(ax, 15.1, 2.2, 15.6, 2.2, color=C_ORANGE)   # corrected
arrow(ax, 9.8,  0.4, 9.8,  1.6, color=C_ORANGE)
arrow(ax, 13.6, 0.4, 13.6, 1.6, color=C_ORANGE)

# outbound → websocket
arrow(ax, 16.35, 2.8, 2.2, 9.8, "outbound call", C_ORANGE)

# ── legend ──────────────────────────────────────────────────────────────────
legend_items = [
    mpatches.Patch(color=C_BLUE,   label="Telephony / Voice IO"),
    mpatches.Patch(color=C_PURPLE, label="LLM Agent (LangGraph + Groq)"),
    mpatches.Patch(color=C_PINK,   label="Agent Tools"),
    mpatches.Patch(color=C_GREEN,  label="Memory & Observability"),
    mpatches.Patch(color=C_ORANGE, label="Outbound Campaigns (Celery)"),
]
ax.legend(handles=legend_items, loc="lower right",
          framealpha=0.15, facecolor=C_BG, edgecolor=C_DIM,
          labelcolor=C_TEXT, fontsize=7.5,
          bbox_to_anchor=(1.0, 0.0))

plt.tight_layout(pad=0.2)
plt.savefig("architecture.png", dpi=150, bbox_inches="tight",
            facecolor=fig.get_facecolor())
print("Saved: architecture.png")
