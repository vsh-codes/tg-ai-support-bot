# Telegram AI Support Bot

Production-ready Telegram bot that turns your knowledge base into a 24/7 customer support agent powered by Anthropic's Claude. Handles real customer questions, knows when to escalate, and never sleeps.

![Python](https://img.shields.io/badge/python-3.12-blue)
![aiogram](https://img.shields.io/badge/aiogram-3.13-blue)
![Claude](https://img.shields.io/badge/Claude-API-orange)
![License](https://img.shields.io/badge/license-MIT-green)
![Docker](https://img.shields.io/badge/docker-ready-blue)

---

## Why this exists

Most "AI chatbot" tools fail in production for the same reason: they answer with confidence even when they shouldn't. Customers get plausible-sounding wrong answers, churn rises, and the company gets blamed for "AI hallucinations."

This bot solves that with three production patterns that most demos skip:

1. **Grounded RAG** — answers come from your own documents, not the model's training data. The system prompt forces the model to cite when it knows and to admit when it doesn't.
2. **Smart escalation** — when confidence is low, the user asks for a human, or the conversation drifts, an admin gets pinged in Telegram with the full transcript and can take over instantly.
3. **Streaming UX** — responses stream into a single Telegram message that updates as the model writes, the same UX as ChatGPT and Claude.ai.

The result is a support agent that customers actually trust, with a clean fallback when it doesn't know.

---

## What it does

- **Answers customer questions** using your own knowledge base files (Markdown, plain text)
- **Semantic search** over your docs via on-device embeddings (no external vector DB required)
- **Conversation memory** — last 10 turns preserved for follow-up questions
- **Streaming responses** that appear word-by-word in Telegram
- **Automatic language detection** — replies in the language the user wrote in
- **Smart escalation** — pings admin when the bot is uncertain, when user asks for a human, or after repeated dead-ends
- **Rate limiting** per user — protects your API budget from abuse
- **Full conversation logging** — every message persisted to SQLite, exportable via /export
- **Admin commands** — /stats, /history, /takeover, /broadcast

---

## Real-world use cases

| Industry | Use case |
|----------|----------|
| **SaaS** | First-line support for product questions, billing, account setup |
| **E-commerce** | Order status, returns policy, product specs |
| **Education** | Course content, schedules, enrollment process |
| **Local services** | Booking, hours, location, pricing |
| **Internal tools** | Employee handbook, IT helpdesk, HR policies |
| **Communities** | Onboarding new members, FAQ for Telegram groups |

---

## Architecture

```
┌──────────────┐    ┌──────────────────┐    ┌────────────────────┐
│   Telegram   │───▶│   aiogram 3      │───▶│   Message Router   │
│    Users     │    │   (long poll)    │    │                    │
└──────────────┘    └──────────────────┘    └─────────┬──────────┘
                                                      │
                  ┌───────────────────────────────────┼──────────────────────┐
                  ▼                                   ▼                      ▼
        ┌──────────────────┐              ┌────────────────────┐  ┌─────────────────┐
        │  Rate Limiter    │              │   RAG Pipeline     │  │   Conversation  │
        │  (per-user/hr)   │              │                    │  │   History (DB)  │
        └──────────────────┘              │  1. Embed query    │  └────────┬────────┘
                                          │  2. Top-K chunks   │           │
                                          │  3. Build context  │           │
                                          └──────────┬─────────┘           │
                                                     │                     │
                                                     ▼                     ▼
                                          ┌────────────────────────────────────┐
                                          │       Claude API (streaming)       │
                                          │  Haiku for cost / Sonnet for depth │
                                          └──────────────────┬─────────────────┘
                                                             │
                                          ┌──────────────────┴─────────────────┐
                                          ▼                                    ▼
                                ┌────────────────────┐                ┌────────────────┐
                                │  Stream → Edit     │                │   Escalation   │
                                │  Telegram message  │                │   Detector     │
                                │  every ~1.5s       │                └────────┬───────┘
                                └────────────────────┘                         │
                                                                               ▼
                                                                    ┌────────────────────┐
                                                                    │  Admin Notification │
                                                                    │  + Transcript link  │
                                                                    └─────────────────────┘
```

---

## Tech stack

- **Python 3.12** — async-first
- **aiogram 3** — modern Telegram framework with FSM, routers, filters
- **anthropic (Claude SDK)** — streaming completions, message API
- **fastembed** — lightweight ONNX-based embeddings, runs on CPU, no GPU required
- **aiosqlite** — async SQLite for conversation history
- **langdetect** — automatic language detection
- **Pydantic Settings** — typed environment config with fail-fast validation
- **Loguru** — structured logging with rotation
- **Docker + docker-compose** — one-command deployment

---

## Quick start

### 1. Prerequisites

- Python 3.12+ (or just Docker)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- An Anthropic API key from [console.anthropic.com](https://console.anthropic.com/)
- Your Telegram user ID for admin notifications (get from [@userinfobot](https://t.me/userinfobot))

### 2. Clone and configure

```bash
git clone https://github.com/vsh-codes/tg-ai-support-bot.git
cd tg-ai-support-bot
cp .env.example .env
# Edit .env with your tokens
```

### 3. Drop your knowledge base into `knowledge/`

Replace the example files in `knowledge/` with your own `.md` or `.txt` files. The bot indexes everything in that directory at startup.

Each file becomes part of the searchable knowledge base. Use Markdown headers to structure topics — the chunker respects them.

### 4. Run (option A: Docker, recommended)

```bash
docker compose up -d
docker compose logs -f
```

### 5. Run (option B: local Python)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m main
```

That's it. Send `/start` to your bot, then ask it anything.

---

## Configuration

All settings live in `.env` (see `.env.example` for the full template):

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | yes | Telegram bot token from @BotFather |
| `ADMIN_CHAT_ID` | yes | Your Telegram user ID (numeric) |
| `ANTHROPIC_API_KEY` | yes | Anthropic API key |
| `CLAUDE_MODEL` | no | Model name (default: `claude-haiku-4-5`) |
| `MAX_HISTORY_TURNS` | no | Conversation history length (default: 10) |
| `RATE_LIMIT_PER_HOUR` | no | Max messages per user per hour (default: 30) |
| `RAG_TOP_K` | no | How many knowledge chunks to retrieve (default: 3) |
| `COMPANY_NAME` | no | Used in system prompt (default: "the company") |
| `KNOWLEDGE_DIR` | no | Path to knowledge files (default: `knowledge/`) |
| `DATABASE_PATH` | no | SQLite file path (default: `data/bot.db`) |
| `LOG_LEVEL` | no | DEBUG / INFO / WARNING / ERROR (default: INFO) |

---

## Model selection

Default is **`claude-haiku-4-5`** — fast and cheap, good for high-volume support workloads.

For higher-stakes conversations (technical depth, sensitive issues), switch to a Sonnet model via `CLAUDE_MODEL=claude-sonnet-4-5`. Cost is ~10-15× higher per token, so use it deliberately.

---

## Admin commands

All admin commands require your Telegram ID to match `ADMIN_CHAT_ID`:

- `/stats` — daily / weekly / total message counts, top users
- `/history <user_id>` — view conversation transcript for a specific user
- `/takeover <user_id>` — temporarily pause the AI for that user; your replies go through directly
- `/broadcast <message>` — send a message to all users who've ever chatted with the bot
- `/reload` — re-index the knowledge base without restart

---

## How RAG works here

1. **Indexing (on startup):** Each file in `knowledge/` is split into ~500-token chunks with 50-token overlap. Each chunk is embedded with `BAAI/bge-small-en-v1.5` via `fastembed`. Embeddings live in memory for fast lookups.

2. **Retrieval (per query):** User's message is embedded the same way. Cosine similarity finds the top-K chunks. These are injected into the system prompt as context.

3. **Generation:** Claude receives the system prompt (with retrieved context), the last N conversation turns, and the user's latest message. The system prompt strictly instructs the model to only answer from the provided context, and to escalate when unsure.

No external vector database, no embedding API calls — everything runs on the same machine as the bot, ~50MB of model weights.

---

## Smart escalation

The bot escalates to admin in three cases:

1. **Explicit request** — user types "human", "agent", "support", "talk to person" (in any language detected)
2. **Low confidence** — model response contains uncertainty markers ("I don't know", "I'm not sure", "I don't have information about")
3. **Repeated dead-ends** — three consecutive messages where the bot can't find relevant context

When escalation triggers, admin gets a Telegram message with:
- User's name and Telegram link
- Last 5 messages in the conversation
- A button to "Take over" the conversation directly

---

## Project structure

```
tg-ai-support-bot/
├── bot/
│   ├── handlers.py       # Command and message handlers
│   ├── messages.py       # User-facing text strings
│   ├── keyboards.py      # Inline keyboards
│   └── escalation.py     # Escalation detection logic
├── ai/
│   ├── client.py         # Claude API streaming wrapper
│   ├── prompts.py        # System prompts
│   ├── knowledge_base.py # Document loader + RAG search
│   └── language.py       # Language detection
├── db/
│   └── storage.py        # SQLite conversation history
├── knowledge/            # Your knowledge base files (.md, .txt)
│   ├── faq.md
│   ├── product.md
│   └── support.md
├── tests/
│   ├── test_knowledge_base.py
│   └── test_language.py
├── config.py             # Pydantic Settings
├── main.py               # Entry point
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env                  # (gitignored)
```

---

## Deployment

The bot is designed to run 24/7 on any small VPS (Hetzner, DigitalOcean, AWS Lightsail).

**Resource footprint:**
- ~250 MB RAM (most of it is the embedding model)
- Negligible CPU at idle, ~1 vCPU peak when generating responses
- Runs comfortably on a $4-6/mo VPS

For production, the included `docker-compose.yml` is ready to go:
- Auto-restart on crash
- Persistent volumes for data and credentials
- No exposed ports (long-polling only — no public IP required)

---

## Cost estimation

With default settings (Haiku model, 30 msg/hr per user, 10-turn history, 3 RAG chunks):

- Average input per turn: ~2,000 tokens (context + history + RAG)
- Average output per turn: ~150 tokens
- **Cost per conversation turn: ~$0.001-0.002**

A bot handling **10,000 customer messages/month** costs approximately **$10-20/month** in Claude API spend. Compare to $300+/mo for an entry-level human agent or $80+/mo for SaaS chatbot platforms.

---

## Roadmap

- [ ] Webhook mode for higher throughput
- [ ] Postgres backend option for multi-instance deployments
- [ ] Optional integration with Zendesk / Intercom for ticket handoff
- [ ] Knowledge base auto-update from Notion / Confluence
- [ ] File attachment support (user uploads → bot reads PDFs/images)
- [ ] Voice message support (Whisper transcription)
- [ ] A/B testing for system prompts

---

## License

MIT — see [LICENSE](LICENSE). Free to use, modify, and deploy commercially.

---

## Contact

Built and maintained by [vsh](https://github.com/vsh-codes).

Available for custom Telegram bot development, AI integrations, RAG systems, and business automation work. For questions or feature requests, open an issue.
