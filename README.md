# Meahana Attendee

A clean, minimal integration for managing meeting bots with real-time transcription and AI-powered reporting.

## Architecture

- **Frontend**: React + TypeScript + Tailwind CSS
- **Backend**: FastAPI + Python + Supabase + Redis
- **Database**: Supabase (REST API)
- **Cache**: Redis for session management

## Quick Start

### Prerequisites

- Node.js 18+ and npm
- Python 3.8+
- Docker and Docker Compose

### Option 1: Full-Stack with Docker (recommended)

```bash
git clone <repository-url>
cd meahana-attendee
cp .env.example .env
nano .env
docker-compose up --build
```

Services:
- Frontend on http://localhost:3000
- Backend API on http://localhost:8000
- Redis on localhost:6379

Note: Set `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_SERVICE_ROLE_KEY` in `backend/.env`.

### Option 2: Development mode

```bash
npm install
cd backend && pip install -r requirements.txt
docker-compose up -d redis
cd backend && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
npm start
```

## Development

### Available scripts (root)

```bash
npm run dev           # frontend + backend (dev)
npm run prod          # frontend + backend (prod)
npm start             # build frontend + start both (prod)
npm run build         # build frontend
npm run install:all   # install frontend + backend deps
```

### Service scripts

```bash
# Frontend
npm run frontend:dev
npm run frontend:build
npm run frontend:prod

# Backend
npm run backend:dev
npm run backend:prod
```

### Frontend development

```bash
cd frontend && npm start
cd frontend && npm run build
```

### Backend development

```bash
npm run backend:dev
npm run backend:docker
```

### Database management

```bash
docker-compose up -d redis
cd backend && alembic upgrade head
cd backend && alembic revision --autogenerate -m "description"
```

The backend uses Supabase REST API for all database operations.

## Production deployment

### Production Docker Compose

```bash
docker-compose -f docker-compose.prod.yml up --build -d
docker-compose -f docker-compose.prod.yml logs -f
docker-compose -f docker-compose.prod.yml down
```

### Production features

- No development reload (stable backend)
- Optimized logging for production
- Production environment defaults
- Health checks via `/health`
- CORS configured for allowed origins

## API endpoints

- `POST /api/v1/bots/` — create a meeting bot
- `GET /api/v1/bots/` — list bots
- `GET /api/v1/bots/{id}` — get a bot
- `DELETE /api/v1/bots/{id}` — delete a bot
- `POST /api/v1/bots/{id}/poll-status` — poll bot status
- `GET /meeting/{id}/scorecard` — get meeting scorecard
- `POST /meeting/{id}/trigger-analysis` — trigger analysis

## Environment variables

Create a `.env` file in the root directory:

```bash
# Backend
ATTENDEE_API_KEY=your_key_here
ATTENDEE_API_BASE_URL=https://app.attendee.dev
ENVIRONMENT=development
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

# Frontend
REACT_APP_API_URL=http://localhost:8000
```

## Docker commands

```bash
docker-compose up --build   # start services
docker-compose up -d        # start in background
docker-compose down         # stop all services
docker-compose logs -f      # follow logs
```

## Project structure

```
meahana-attendee/
├── frontend/              # React frontend
│   ├── src/               # Components, services, types
│   ├── package.json       # Frontend dependencies/scripts
│   └── Dockerfile         # Frontend container
├── backend/               # FastAPI backend
│   ├── app/               # Application code
│   ├── alembic/           # Database migrations
│   ├── requirements.txt   # Backend dependencies
│   └── Dockerfile         # Backend container
├── docker-compose.yml     # Dev orchestration
├── docker-compose.prod.yml# Prod orchestration
└── package.json           # Monorepo scripts (frontend/backend)
```

## Features

- Bot management
- Real-time status updates
- AI-powered meeting insights and scorecards
- Modern UI with Tailwind CSS
- Full TypeScript support for frontend and backend typings

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test with `npm run dev`
5. Submit a pull request

## License

This project is licensed under the MIT License.

