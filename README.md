# Municipal Voicebot Agent (Comune di Codroipo)

Voice-agent tools for the Italian municipality of **Codroipo (UD, Friuli-Venezia Giulia)**, exposed as
**MCP tools** over HTTP so a [Vapi.ai](https://vapi.ai) voice agent can use them. A citizen can ask
questions answered from municipal documents (hybrid lexical + vector retrieval) and book, check, edit or
cancel appointments. Every tool answers in Italian.

The whole stack runs locally with `docker compose` and is published to the internet with `ngrok`.

## Architecture

```
                 ngrok (https)                 docker compose network
Vapi agent  ───────────────────▶  mcp  ───────────────┬────────────▶  db (Postgres + pgvector)
                              (FastMCP, /mcp)          └────────────▶  embedder (Qwen3-Embedding-0.6B)
                                                                          ▲
host:  scripts/ingest.py  ────────────────────────────────────────────── ┘
       (reads data/documents/*.html, chunks, embeds, loads Postgres)
```

- **db**: a single Postgres (`pgvector/pgvector`) with two schemas: `docs` (documents + chunks) and
  `booking` (appointments + cancellation log). Schema is auto-applied from `db/init/*.sql` on first boot.
- **embedder**: a small FastAPI service wrapping `Qwen/Qwen3-Embedding-0.6B` (1024-dim). Both the ingestion
  script and the MCP server call it, so text is embedded identically at write and query time.
- **mcp**: the FastMCP server exposing the tools at `/mcp` (Streamable HTTP).
- **ngrok**: a public HTTPS tunnel to `mcp`; the resulting URL is what you register in Vapi.

## Retrieval

Hybrid search combines native Italian full-text (`to_tsvector('italian', ...)`, BM25-style lexical) with
pgvector cosine similarity, fused by weighted Reciprocal Rank Fusion. Two knobs (env):

- `RETRIEVAL_ALPHA` (0.0 to 1.0): weight of the vector arm vs the lexical arm. `0.5` is balanced.
- `VECTOR_SEARCH_ENABLED`: set `false` to run lexical-only search. Setting `RETRIEVAL_ALPHA=0` does the same.

## Appointments

A single shared municipal calendar with fixed-duration slots (`APPOINTMENT_DURATION_MINUTES`, default 30)
inside configurable office hours. Two appointments may not overlap; this is enforced by a Postgres exclusion
constraint and pre-checked by the tools so the citizen gets a friendly Italian message and alternative slots.

When an appointment is cancelled it is first copied into `booking.cancelled_appointments` (so the operator
never loses information) and then removed. The `notification_required` flag on that table marks rows whose
confirmation email has not been sent: **an `AFTER INSERT` trigger on this table could enqueue an email asking
the citizen to confirm the cancellation.** This is a documented extension point and is not wired up.

## Tools

| Tool | Purpose |
|---|---|
| `search_documentation` | Answer a citizen question from the municipal documents. |
| `get_available_slots` | List free appointment slots for a day. |
| `create_appointment` | Book an appointment (asks, in Italian, for any missing mandatory field). |
| `check_appointments` | Look up appointments by phone, surname, or day. |
| `edit_appointment` | Change an appointment (re-checks for overlaps). |
| `cancel_appointment` | Cancel after confirmation; logs the cancellation. |

## Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for the host ingestion script and tests)
- An ngrok account / authtoken (only needed to expose the server publicly)

## Quick start

```bash
# 1. Configure
cp .env.example .env        # edit NGROK_AUTHTOKEN if you want the tunnel

# 2. Start the database and the embedding service
#    (first embedder boot downloads ~1.2GB model weights into ./models)
docker compose up -d db embedder

# 3. Ingest the documents from the host (points at the published container ports)
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
PG_HOST=localhost EMBEDDING_SERVICE_URL=http://localhost:8001 python scripts/ingest.py --reset

# 4. Start the MCP server and the public tunnel
docker compose up -d mcp ngrok
```

The MCP endpoint is now at `http://localhost:8000/mcp`. The public ngrok URL is shown at
`http://localhost:4040` (the ngrok inspection UI).

Optional: pre-download the model before starting the embedder with
`pip install huggingface_hub && python scripts/download_model.py`.

## Register the tools in Vapi

In your Vapi assistant, add a tool of type `mcp` pointing at your public URL plus `/mcp`:

```json
{
  "type": "mcp",
  "function": { "name": "mcpTools" },
  "server": {
    "url": "https://<your-subdomain>.ngrok-free.app/mcp",
    "headers": { "Authorization": "Bearer <MCP_AUTH_TOKEN>" }
  },
  "metadata": { "protocol": "shttp" }
}
```

The `headers` block is only needed if you set `MCP_AUTH_TOKEN` in `.env` (it is empty by default). Vapi
connects over Streamable HTTP and discovers the tools automatically.

## Local smoke test (without Vapi)

```python
import asyncio
from fastmcp import Client

async def main():
    async with Client("http://localhost:8000/mcp") as client:
        print(await client.call_tool("search_documentation",
                                     {"query": "Quali sono gli orari dell'ufficio anagrafe?"}))

asyncio.run(main())
```

## Configuration

All settings come from the environment (see `.env.example` for the full list and defaults). The most useful:

| Variable | Default | Meaning |
|---|---|---|
| `RETRIEVAL_ALPHA` | `0.5` | Vector vs lexical weight (0 = lexical only). |
| `VECTOR_SEARCH_ENABLED` | `true` | Hard switch for the vector arm. |
| `APPOINTMENT_DURATION_MINUTES` | `30` | Fixed slot length. |
| `OFFICE_OPEN_DAYS` / `OFFICE_OPEN_TIME` / `OFFICE_CLOSE_TIME` | `0,1,2,3,4` / `09:00` / `12:30` | Bookable office hours. |
| `MCP_AUTH_TOKEN` | empty | If set, requests must send `Authorization: Bearer <token>`. |

## Tests

```bash
pip install -e ".[dev]"

# Fast unit tests (no database needed)
pytest -m "not integration"

# Full suite, including integration tests (needs Postgres up)
docker compose up -d db
PG_HOST=localhost pytest
```

Unit tests cover the chunker, retrieval fusion decision and Italian formatting, slot math, and the
appointment validation messages. Integration tests apply the schema to a disposable `municipal_test`
database and drive the tools through the in-memory FastMCP client.

## Notes

- Prompts and docstrings are in English (they form the tool schema the agent reads); every response to the
  citizen is in Italian.
- Document content is realistic but invented for the demo. Note the local specifics: Friuli-Venezia Giulia
  uses **ILIA** (not IMU), and Codroipo uses **TARIC via A&T 2000** (not TARI).
