# Meahana Attendee

A FastAPI backend for managing meeting bots with real-time transcription, AI-powered reporting, and outgoing report webhooks.

## Architecture

- **Backend**: FastAPI + Python
- **Database / Auth**: Supabase (REST API + Auth + RLS)
- **AI Analysis**: OpenAI GPT-4o-mini
- **Tunneling**: Ngrok (for local webhook development)

## Quick Start

### Prerequisites

- Python 3.10+

### Setup

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Supabase, Attendee, and OpenAI credentials

# Start the server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`.

## API Endpoints

### Auth

- `POST /api/v1/auth/signup` -- Create user
- `POST /api/v1/auth/signin` -- Sign in
- `POST /api/v1/auth/signout` -- Sign out
- `GET /api/v1/auth/me` -- Current user

### Bots

- `POST /api/v1/bots/` -- Create a meeting bot
- `GET /api/v1/bots/` -- List bots
- `GET /api/v1/bots/{id}` -- Get a bot
- `DELETE /api/v1/bots/{id}` -- Delete a bot
- `POST /api/v1/bots/{id}/poll-status` -- Poll bot status

### Reports

- `GET /meeting/{id}/scorecard` -- Get meeting scorecard
- `POST /meeting/{id}/trigger-analysis` -- Trigger analysis

### Webhooks

- `POST /webhook/` -- Receive Attendee.dev webhook events
- `GET /webhook/url` -- Get current webhook URL

### Health

- `GET /health` -- Health check

## Outgoing Report Webhook

After a meeting finishes and the AI analysis completes, the backend can POST the scorecard to a configured URL.

Set these in your `.env`:

```bash
REPORT_WEBHOOK_URL=https://your-endpoint.example.com/webhook
REPORT_WEBHOOK_SIGNING_SECRET=your_secret_here   # optional, for HMAC-SHA256 verification
```

The payload is a JSON object with the event type, meeting details, and full scorecard. See `app/schemas/schemas.py` (`ReportWebhookPayload`) for the exact shape.

## Environment Variables

See `backend/.env.example` for all available configuration options.

## Project Structure

```
backend/
├── app/
│   ├── core/           # Config, database
│   ├── models/         # SQLAlchemy models (legacy reference)
│   ├── prompts/        # AI analysis prompt templates
│   ├── routers/        # API route handlers
│   ├── schemas/        # Pydantic request/response schemas
│   ├── services/       # Business logic
│   └── main.py         # FastAPI app entry point
├── alembic/            # Database migrations
├── requirements.txt    # Python dependencies
├── Dockerfile          # Container image
└── .env.example        # Environment variable template
```

## License

This project is licensed under the MIT License.
