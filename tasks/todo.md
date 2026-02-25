# LearnSpark — Task Tracker

## Session 1: Backend Skeleton (DONE)
- [x] Cleanup root misc files → misc/
- [x] Verify learnspark/ folder structure
- [x] Write backend requirements.txt (8 deps)
- [x] Build config.py — Pydantic BaseSettings, loads .env
- [x] Build models.py — 18 Pydantic models, all validated
- [x] Full verification pass

## Session 2: API Clients + Prompts (DONE)
- [x] Research Venice AI API docs (image, TTS, vision, chat endpoints)
- [x] Build prompts.py — all LLM prompt templates
- [x] Build akashml_client.py — DeepSeek V3.2 + Llama 3.3 70B
- [x] Build venice_client.py — image gen, TTS, vision, chat
- [x] Fixed config.py: TTS voice natasha → af_heart (Kokoro Grade A)
- [x] Added LearnSpark env vars to .env (Venice placeholders)

## Session 3: Pipeline + Server (DONE)
- [x] Build pipeline.py — 5-stage orchestrator with asyncio.Queue event bus
- [x] Build main.py — FastAPI server with SSE streaming
- [x] All endpoints tested: /health, /api/generate (SSE), /api/examples, /api/journey

## Session 4: React Frontend (DONE)
- [x] Vite + React 18 + Tailwind v4 project scaffold
- [x] Glassmorphism design system in index.css (@theme tokens, .glass, .glow-*, .skeleton)
- [x] useGeneration SSE hook — connects to POST /api/generate, parses all event types
- [x] PromptInput — hero landing page with gradient text, glassmorphism input, example chips
- [x] PipelineProgress — 5-stage animated progress bar with active/done/pending states
- [x] StepCard — learning step with image, text, metaphor, audio player, vision badge
- [x] AudioPlayer — play/pause TTS audio from base64 data URI
- [x] VisionBadge — color-coded quality score from Venice Vision
- [x] Quiz — interactive multiple-choice with correct/incorrect feedback
- [x] ConceptMap — SVG circle layout with animated nodes and edges
- [x] App.jsx — landing ↔ journey view transition with AnimatePresence
- [x] Verified: clean build (0 errors), frontend serves at :5173, proxy to :8000 works

## Session 5: E2E Integration + Visual Polish (DONE)
- [x] End-to-end smoke test: backend + frontend running, SSE events verified
- [x] Fixed AkashML timeout: increased from 60s to 120s, fixed empty error messages
- [x] Pipeline test: 5 step_text + 4 quiz questions + concept map (5 nodes, 8 edges) all arrive correctly
- [x] Venice errors degrade gracefully (no API key) — no crashes, clean placeholders
- [x] PipelineProgress: sticky positioning, Framer Motion glow pulse, animated gradient connecting lines, completion flash, Volume2 icon for narration
- [x] StepCard: rich skeleton with shimmer, "Generating illustration..." placeholder with spinning icon + dots, "Generating narration..." with waveform bars, image glow-on-load, staggered content animations, responsive flex-col/flex-row
- [x] Quiz: header with icon badge + gradient divider, score tracker with progress bar, spring-animated check/x icons, completion message, radio-button-style option indicators
- [x] ConceptMap: "How It All Connects" header, SVG stroke-dasharray draw animation, hover glow + scale, click-to-scroll to step cards, gradient edges
- [x] App.jsx: landing scale-down exit, journey fade-up entrance, "Complete" badge with spring animation, error details list, data-step-index for scroll targets
- [x] Error state UI: styled "Illustration unavailable" / "Narration unavailable" placeholders (not broken icons)
- [x] Responsive: mobile text sizes, flex-col breakpoints, hidden labels on small screens
- [x] CSS: fixed background gradient, smooth scroll behavior
- [x] Final build: 295KB JS + 31.6KB CSS, 0 errors

## Session 6: Docker + Akash SDL (DONE)
- [x] config.py: env_file path only loads if .env exists (Docker gets env vars directly)
- [x] Backend Dockerfile: python:3.11-slim, curl for healthcheck, layer-cached pip install
- [x] Frontend Dockerfile: two-stage (node:20-alpine build → nginx:alpine serve)
- [x] nginx.conf.template: API proxy with SSE support (proxy_buffering off, Connection ''), SPA fallback, gzip, cache headers
- [x] docker-entrypoint.sh: envsubst templates BACKEND_URL into nginx config at start
- [x] Fixed Windows \r\n line endings in entrypoint (sed -i 's/\r$//')
- [x] docker-compose.yaml: backend (8000) + frontend (3000→80), env_file from root .env, healthcheck
- [x] Akash SDL: two-service deployment (backend internal, frontend global:true on port 80)
- [x] .dockerignore for both services
- [x] docker compose up --build: both containers running, backend healthy
- [x] Verified: localhost:3000 serves HTML, /health proxied, /api/examples proxied, SSE streaming works through nginx

## Session 7: MiniMax Client + Provider Toggle (DONE)
- [x] Researched MiniMax APIs: image gen (image-01), TTS (speech-2.8-hd), NO vision (mocked)
- [x] Built minimax_client.py — same interface as venice_client (generate_image, generate_speech, analyze_image)
- [x] MiniMax image gen: POST /v1/image_generation, response_format: "base64"
- [x] MiniMax TTS: POST /v1/t2a_v2, hex-encoded audio decoded with bytes.fromhex()
- [x] MiniMax vision: returns mock VisionScore (no vision API available)
- [x] Updated config.py: minimax_api_key, minimax_api_base, minimax_tts_voice, media_provider
- [x] Created media_provider.py: factory returns MiniMaxClient or VeniceClient based on MEDIA_PROVIDER env var
- [x] Updated pipeline.py: self._venice → self._media (provider-agnostic)
- [x] Updated main.py: uses create_media_client() factory, logs active provider
- [x] Updated .env: MiniMax API key, base URL, TTS voice, MEDIA_PROVIDER=minimax
- [x] Individual MiniMax tests: image (17.1s, 120KB), TTS (2.9s, 214KB), vision mock — all PASS
- [x] Fixed rate limiting: asyncio.Semaphore(2) + 0.5s request gap + 0.3s step stagger + 1s retry backoff
- [x] Full pipeline test: 4 step_text + 4 step_image + 4 step_audio + 4 step_vision + quiz + concept_map — ZERO ERRORS (136.7s)
- [x] Updated Akash SDL with MiniMax env vars
- [x] docker-compose.yaml: already uses env_file from root .env (no changes needed)

## Session 8: Browser Verification + Docker Rebuild + Push (DONE)
- [x] Code review: verified useGeneration.js SSE parsing, StepCard image rendering, AudioPlayer, VisionBadge
- [x] Fixed AudioPlayer: switched from raw data URI to Blob URL for reliable large audio playback
- [x] Fixed minimax_client.py: audio content_type "audio/mp3" → "audio/mpeg" (standard MIME)
- [x] SSE proxy test: full pipeline through Vite proxy (:5173) — 5 steps, all images + audio + vision, zero errors
- [x] Docker rebuild: docker compose up --build — both images built, containers healthy
- [x] Docker pipeline test through nginx (:3000) — 4 steps, all images + audio + vision, zero errors, audio/mpeg confirmed
- [x] Docker Hub push: xploitkid/learnspark-backend:latest + xploitkid/learnspark-frontend:latest
- [x] Created .env.example with all env vars documented

## Docker Build & Push Commands
```bash
# From learnspark/deploy directory:
docker compose up --build        # builds + runs locally
docker compose down               # stop

# Or manual build + push from learnspark/ directory:
docker build -t xploitkid/learnspark-backend:latest ./backend
docker build -t xploitkid/learnspark-frontend:latest ./frontend
docker push xploitkid/learnspark-backend:latest
docker push xploitkid/learnspark-frontend:latest
```

## Session 9: Multi-View UI Redesign (DONE)
- [x] Created BottomNav — fixed bottom tab bar with Steps/Quiz/Map, sliding indicator
- [x] Created ViewShell — shared layout wrapper (top bar, content area, bottom nav)
- [x] Created StepViewer — single-step slideshow with Prev/Next, keyboard arrows, step dots, large images
- [x] Created QuizView — one question at a time with progress bar, score, results screen
- [x] Created ConceptMapView — thin wrapper, node click navigates to step
- [x] Modified ConceptMap — added onNodeClick prop
- [x] Created PipelineDiagram — animated vertical flowchart with parallel stage row, glow effects, flowing dots, progress counters
- [x] Rewrote App.jsx — 5-view router (landing → pipeline → steps|quiz|conceptmap), auto-transitions
- [x] Build: 300KB JS + 36KB CSS, 0 errors
- [x] Docker rebuild: both containers healthy
- [x] Docker Hub push: xploitkid/learnspark-backend:latest + xploitkid/learnspark-frontend:latest

## Session 10: Conversational UI Redesign (DONE)
- [x] Created sanitize.js — strips em dashes, en dashes, double hyphens from all AI text
- [x] Updated prompts.py — added "NEVER use em dashes" rule to both LLM prompts
- [x] Created TopBar — sticky header with LearnSpark logo + AkashGuard status indicator
- [x] Created BottomInput — sticky bottom input bar for follow-up questions
- [x] Created LearningFeed — main conversational feed orchestrator with auto-scroll
- [x] Created FeedPipelineCard — compact inline 5-stage pipeline progress
- [x] Created FeedStepCard — rich step card with full-width image, explanation, metaphor callout, compact audio
- [x] Created FeedQuizCard — inline one-at-a-time quiz with auto-advance, shake on wrong, score card
- [x] Rewrote ConceptMap — real interactive SVG graph with pentagon layout, curved bezier edges, hover dimming, click-to-scroll
- [x] Rewrote AudioPlayer — compact play/pause button with animated waveform bars
- [x] Rewrote App.jsx — landing ↔ conversational feed layout (TopBar + Feed + BottomInput)
- [x] Updated PromptInput — new tagline "Ask anything. Learn visually."
- [x] Build: 296KB JS + 41KB CSS, 0 errors
- [x] Docker rebuild: both containers healthy
- [x] Docker Hub push: xploitkid/learnspark-backend:latest + xploitkid/learnspark-frontend:latest

## Blocking: Venice API Key
- [ ] Add VENICE_API_KEY to .env to unblock Venice image/TTS/vision (currently using MiniMax)

## Next Up
- [ ] Deploy to Akash Network via Akash Console
- [ ] AkashGuard integration (monitor LearnSpark health endpoint)
