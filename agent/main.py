import asyncio
import base64
import io
import logging
import time
from pathlib import Path
from typing import Any

from agent.config import settings
from agent.database import (
    add_service,
    get_all_services,
    get_recent_health_checks,
    get_service,
    init_db,
    update_service_deployment,
)
import agent.event_bus as bus
from agent.health_checker import HealthChecker
from agent.llm_engine import DiagnosisEngine
from agent.notifier import TelegramNotifier
from agent.recovery_engine import RecoveryEngine

logger = logging.getLogger("akashguard.agent")

REDEPLOY_CONFIDENCE_THRESHOLD = 0.7

# Module-level dict: service_name -> remaining fake failures
simulate_failures: dict[str, int] = {}

# Post-recovery cooldown: service_name -> timestamp when cooldown expires
recovery_cooldowns: dict[str, float] = {}
RECOVERY_COOLDOWN_SECONDS = 120


class AkashGuardAgent:

    def __init__(self) -> None:
        self.health_checker = HealthChecker()
        self.diagnosis_engine = DiagnosisEngine()
        self.recovery_engine = RecoveryEngine()
        self.notifier = TelegramNotifier()
        self.running = False

    async def start(self) -> None:
        init_db()
        self.running = True
        logger.info("AkashGuard agent started, interval=%ds", settings.health_check_interval)
        try:
            await self.run_loop()
        finally:
            await self._cleanup()

    async def run_loop(self) -> None:
        while self.running:
            try:
                await self.monitor_cycle()
            except Exception as exc:
                logger.error("monitor cycle failed: %s", exc)
            await asyncio.sleep(settings.health_check_interval)

    async def monitor_cycle(self) -> None:
        results = await self.health_checker.check_all_services()

        # Check for simulated failures, override real results
        for r in results:
            name = r["service_name"]
            if name in simulate_failures and simulate_failures[name] > 0:
                r["is_healthy"] = False
                r["status_code"] = 503
                r["error_message"] = "Simulated failure (demo mode)"
                r["response_time_ms"] = None
                simulate_failures[name] -= 1
                if simulate_failures[name] <= 0:
                    del simulate_failures[name]
                # Re-record the fake result
                from agent.database import record_health_check
                try:
                    record_health_check(
                        service_id=r["service_id"],
                        status_code=503,
                        response_time_ms=None,
                        is_healthy=False,
                        error_message="Simulated failure (demo mode)",
                    )
                except Exception:
                    pass

        # Emit health_check events, suppress during cooldown
        for r in results:
            name = r["service_name"]
            if name in recovery_cooldowns:
                remaining = recovery_cooldowns[name] - time.time()
                if remaining > 0:
                    continue
                del recovery_cooldowns[name]
            bus.emit("health_check", {
                "service": name,
                "status": "healthy" if r["is_healthy"] else "unhealthy",
                "status_code": r.get("status_code"),
                "response_time_ms": r.get("response_time_ms"),
                "error": r.get("error_message"),
            })

        services = get_all_services()
        for svc in services:
            try:
                await self._evaluate_and_act(svc)
            except Exception as exc:
                logger.error("evaluate_and_act failed for %s: %s", svc["name"], exc)

    async def _evaluate_and_act(self, svc: dict[str, Any]) -> None:
        sid = svc["id"]
        name = svc["name"]
        prev_status = svc.get("status", "unknown")

        # Skip evaluation if service is in post-recovery cooldown
        if name in recovery_cooldowns:
            remaining = recovery_cooldowns[name] - time.time()
            if remaining > 0:
                logger.info("service=%s in cooldown (%.0fs remaining)", name, remaining)
                bus.emit("health_check", {
                    "service": name,
                    "status": "cooldown",
                    "remaining": round(remaining),
                })
                return
            del recovery_cooldowns[name]

        status, recent = self.health_checker.evaluate_service_health(sid)

        if status == "healthy":
            logger.info("service=%s status=healthy", name)
            if prev_status in ("down", "degraded", "recovering"):
                bus.emit("service_healthy", {"service": name})
            return

        if status == "unknown":
            logger.info("service=%s status=unknown (no checks yet)", name)
            return

        # Consecutive failures count
        failures = sum(1 for c in recent if not c["is_healthy"])
        bus.emit("service_down", {
            "service": name,
            "status": status,
            "consecutive_failures": failures,
        })

        # Telegram: notify on first failure
        if failures == 1:
            await self.notifier.notify_first_failure(name, "Health check failed")

        # Telegram: notify when threshold hit
        if failures == settings.failure_threshold:
            await self.notifier.notify_threshold_hit(name, failures, settings.failure_threshold)

        # Emit health_streak when nearing or hitting threshold
        bus.emit("health_streak", {
            "service": name,
            "consecutive_failures": failures,
            "threshold": settings.failure_threshold,
        })

        logger.warning("service=%s status=%s, requesting LLM diagnosis", name, status)

        bus.emit("diagnosis_start", {"service": name})

        checks = get_recent_health_checks(sid, limit=10)
        diagnosis = await self.diagnosis_engine.diagnose(
            service_id=sid,
            service_name=name,
            health_status=status,
            recent_checks=checks,
        )

        action = diagnosis["recommended_action"]
        confidence = diagnosis["confidence"]
        decision_id = diagnosis.get("decision_id")

        bus.emit("diagnosis", {
            "service": name,
            "diagnosis": diagnosis["diagnosis"],
            "confidence": confidence,
            "recommended_action": action,
            "reasoning": diagnosis.get("reasoning", ""),
        })

        # Emit the decision summary
        bus.emit("llm_decision", {
            "service": name,
            "action": action,
            "confidence": confidence,
            "reasoning_summary": diagnosis.get("reasoning", "")[:200],
        })

        logger.info(
            "service=%s llm_action=%s confidence=%.2f diagnosis=%s",
            name, action, confidence, diagnosis["diagnosis"],
        )

        # Telegram: notify LLM decision
        await self.notifier.notify_llm_decision(name, diagnosis)

        if action != "redeploy":
            logger.info("service=%s action=%s, no recovery needed", name, action)
            return

        if confidence < REDEPLOY_CONFIDENCE_THRESHOLD:
            logger.info(
                "service=%s confidence=%.2f < threshold=%.2f, skipping redeploy",
                name, confidence, REDEPLOY_CONFIDENCE_THRESHOLD,
            )
            return

        sdl = self._load_sdl(svc)
        if not sdl:
            logger.error("service=%s has no SDL, cannot redeploy", name)
            return

        detection_time = time.time()
        old_dseq = svc.get("current_dseq")

        bus.emit("recovery_start", {
            "service": name,
            "reason": diagnosis["diagnosis"],
            "old_dseq": old_dseq,
        })

        logger.info("service=%s initiating recovery (confidence=%.2f)", name, confidence)
        t0 = time.monotonic()
        result = await self.recovery_engine.recover_service(
            service_id=sid,
            sdl=sdl,
            old_dseq=old_dseq,
            decision_id=decision_id,
            service_name=name,
        )

        await self.notifier.notify_recovery_complete(
            name, result, diagnosis=diagnosis, detection_time=detection_time,
        )

        if result["success"]:
            recovery_cooldowns[name] = time.time() + RECOVERY_COOLDOWN_SECONDS
            logger.info("service=%s cooldown set for %ds", name, RECOVERY_COOLDOWN_SECONDS)
            total_time = result.get("total_time_seconds", round(time.monotonic() - t0, 1))
            new_uri = (result.get("uris") or [""])[0]
            bus.emit("recovery_complete", {
                "service": name,
                "new_dseq": result.get("new_dseq"),
                "new_uri": new_uri,
                "provider": result.get("provider"),
                "total_time_seconds": total_time,
            })
            logger.info(
                "service=%s recovery succeeded new_dseq=%s provider=%s uris=%s",
                name, result["new_dseq"], result["provider"], result["uris"],
            )

            # Vision-based health verification (background task)
            if new_uri:
                asyncio.create_task(
                    self._vision_verify(name, new_uri),
                    name=f"vision-verify-{name}",
                )
        else:
            bus.emit("recovery_failed", {
                "service": name,
                "error": result.get("error", "Unknown error"),
                "step": "recovery",
            })
            logger.error("service=%s recovery failed: %s", name, result["error"])

    async def _vision_verify(self, service_name: str, uri: str) -> None:
        """Wait 20s, screenshot the service, send to Venice vision, report via Telegram."""
        logger.info("service=%s vision verification scheduled, waiting 20s for boot", service_name)
        await asyncio.sleep(20)

        url = uri if uri.startswith("http") else f"http://{uri}"
        screenshot_b64 = await self._capture_screenshot(url)

        if not screenshot_b64:
            logger.warning("service=%s vision verification skipped: screenshot capture failed", service_name)
            return

        assessment = await self.notifier.venice.vision(
            screenshot_b64,
            "Is this web service functioning correctly? Check if the page loaded properly, shows expected content, and has no error messages.",
        )

        if not assessment:
            logger.warning("service=%s vision verification skipped: vision API unavailable", service_name)
            return
        logger.info("service=%s vision verification complete: %s", service_name, assessment)

    @staticmethod
    async def _capture_screenshot(url: str) -> str | None:
        """Capture a screenshot. Try playwright first, fall back to httpx HTML fetch."""
        # Try playwright
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1280, "height": 720})
                await page.goto(url, timeout=15000, wait_until="domcontentloaded")
                await asyncio.sleep(2)
                screenshot_bytes = await page.screenshot(type="png")
                await browser.close()
                return base64.b64encode(screenshot_bytes).decode("ascii")
        except Exception as exc:
            logger.warning("Playwright screenshot failed (%s), trying httpx fallback", exc)

        # Fallback: fetch HTML, render as simple image for vision model
        try:
            import httpx as _httpx
            async with _httpx.AsyncClient(timeout=_httpx.Timeout(10.0)) as client:
                resp = await client.get(url)
                html = resp.text[:2000]
                from PIL import Image, ImageDraw, ImageFont
                img = Image.new("RGB", (800, 400), (255, 255, 255))
                draw = ImageDraw.Draw(img)
                font = ImageFont.load_default()
                draw.text((20, 20), f"URL: {url}", fill=(0, 0, 0), font=font)
                draw.text((20, 40), f"Status: {resp.status_code}", fill=(0, 0, 0), font=font)
                lines = html.split("\n")[:15]
                y_pos = 70
                for line in lines:
                    draw.text((20, y_pos), line[:100], fill=(0, 0, 0), font=font)
                    y_pos += 18
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                return base64.b64encode(buf.read()).decode("ascii")
        except Exception as exc2:
            logger.error("httpx fallback screenshot also failed: %s", exc2)
            return None

    @staticmethod
    def _load_sdl(svc: dict[str, Any]) -> str | None:
        sdl = svc.get("sdl_template")
        if not sdl:
            return None

        # If it looks like a file path, read the contents
        if sdl.rstrip().endswith((".yaml", ".yml")):
            try:
                return Path(sdl).read_text()
            except Exception as exc:
                logger.error("failed to read SDL file %s: %s", sdl, exc)
                return None

        # Otherwise it's inline SDL content
        return sdl

    def register_service(
        self,
        name: str,
        health_url: str,
        sdl_path: str | None = None,
        current_dseq: str | None = None,
        current_provider: str | None = None,
    ) -> int:
        sdl_content: str | None = None
        if sdl_path:
            path = Path(sdl_path)
            if path.exists():
                sdl_content = path.read_text()
                logger.info("loaded SDL from %s (%d bytes)", sdl_path, len(sdl_content))
            else:
                logger.warning("SDL file not found: %s", sdl_path)

        sid = add_service(name, health_url, sdl_content)
        logger.info("registered service=%s id=%d health_url=%s", name, sid, health_url)

        if current_dseq and current_provider:
            update_service_deployment(sid, current_dseq, current_provider)

        return sid

    async def stop(self) -> None:
        self.running = False
        logger.info("AkashGuard agent stopping")
        await self._cleanup()

    async def _cleanup(self) -> None:
        await self.health_checker.close()
        await self.recovery_engine.close()
        await self.notifier.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    agent = AkashGuardAgent()
    asyncio.run(agent.start())


if __name__ == "__main__":
    main()
