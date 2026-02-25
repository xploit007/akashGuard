# LearnSpark — Lessons Learned

## Venice AI API
- Native image endpoint is `/image/generate` (NOT `/images/generations`) — returns `{"images": ["<b64>"]}`
- TTS returns **raw binary bytes**, not JSON — must `base64.b64encode(resp.content)`
- TTS model is `tts-kokoro`, best voice is `af_heart` (Grade A, warm female)
- Vision uses standard chat completions with OpenAI vision format (content array)
- Set `venice_parameters.include_venice_system_prompt: false` to prevent persona interference
- Empty API key causes `Illegal header value b'Bearer '` — httpx rejects it before sending

## AkashML API
- OpenAI-compatible format, works with httpx direct calls
- DeepSeek V3.2 learning path gen: ~55s for 5 steps (2600 tokens)
- Llama 3.3 70B quiz gen: ~39s for 4 questions (1900 tokens)
- Both models reliably return valid JSON when prompted correctly
- Markdown fence stripping needed — models sometimes wrap in ```json blocks

## Pipeline Architecture
- asyncio.Queue as event bus works well for parallel-to-generator bridge
- Per-step pattern: image + TTS start in parallel, vision fires after image completes
- Sentinel values (None) in queue to track step completion count
- Total pipeline time with AkashML only (no Venice): ~86-100s
- sse-starlette auto-sends heartbeat pings — good for keeping connections alive

## MiniMax API
- Image gen: POST /v1/image_generation, model "image-01", request `response_format: "base64"`
- Response: `data.data.image_base64[0]` (array of base64 strings)
- TTS: POST /v1/t2a_v2, model "speech-2.8-hd", returns hex-encoded audio in `data.data.audio`
- Decode TTS: `bytes.fromhex(hex_string)` then base64-encode for frontend
- Voice: `English_CaptivatingStoryteller` (warm storyteller voice)
- NO vision API — must mock for testing, use Venice for production
- **Rate limiting is aggressive**: 10 concurrent calls all fail, but individual calls succeed
- Fix: asyncio.Semaphore(2) + 0.5s gap between requests + 0.3s stagger between pipeline steps
- Individual call times: image ~17-21s, TTS ~3-4s
- Full pipeline with rate limiting: 4 steps in ~87s for stages 2-4

## Provider Abstraction
- Factory pattern in media_provider.py — returns MiniMaxClient or VeniceClient based on MEDIA_PROVIDER env var
- Both clients must implement: generate_image(), generate_speech(), analyze_image() — same signatures
- Pipeline uses duck-typing (no explicit interface) — just call self._media.method()
- Switch providers by changing one env var — no code changes needed

## Windows Bash Gotchas
- Chaining commands with `&&` after `&` (backgrounding) breaks on Git Bash for Windows
- Use separate Bash calls instead of complex one-liners when backgrounding processes
- When killing uvicorn with --reload: must kill both parent and child PIDs
- Server redirect with `>` may not capture child process output — use `tee` or run without --reload for debugging
- `taskkill //F //PID` sometimes fails on stale netstat entries — verify with `tasklist`
