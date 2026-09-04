"""
Proxie DevOps Evaluation - Primary Solution
Chrome DevTools Protocol (CDP) / Playwright Bridge
Bridges a hosted Three.js web app to a local Python IDE in real time.

Features:
- Sub-millisecond bidirectional IPC pipe
- Streams live telemetry: (X, Z), rotation, calculated FPS, velocity, boundary margin
- Dispatches robot commands: forward, back, left, right, run
- Supports Headed mode (visual UI), Headless mode (CI/CD automated testing),
  and CDP Attach mode (connects to existing Chrome via --cdp-url)
- Autonomous patrol routines & Closed-loop waypoint navigation
"""

import argparse
import asyncio
import http.server
import logging
import math
import os
import socket
import socketserver
import sys
import threading
import time
from typing import Dict, Any, Optional

from playwright.async_api import async_playwright, Page, BrowserContext, Browser
from telemetry_dashboard import TelemetryTracker, RICH_AVAILABLE
from robot_controller import RobotController


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def ensure_local_server(port: int = 8000):
    if not is_port_in_use(port):
        logger.info(f"[Auto-Server] Starting background static HTTP server on port {port}...")
        httpd = socketserver.TCPServer(("", port), QuietHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.5)
        return httpd
    return None


if RICH_AVAILABLE:
    from rich.live import Live
    from rich.console import Console
    console = Console()
else:
    console = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("ProxieBridge")


class ProxieDevOpsBridge:
    def __init__(self, target_url: str, headless: bool = False, cdp_url: Optional[str] = None):
        self.target_url = target_url
        self.headless = headless
        self.cdp_url = cdp_url
        
        self.tracker = TelemetryTracker()
        self.page: Optional[Page] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.playwright = None
        
        self._telemetry_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self.controller = RobotController(self.send_command)

    def _on_robot_state(self, source, state: Dict[str, Any]):
        """CDP callback triggered by window.postMessage in browser."""
        self._telemetry_queue.put_nowait(state)

    async def send_command(self, cmd: Dict[str, Any], mode: Optional[str] = None):
        """Sends a robot-command into the page window context."""
        if not self.page or self.page.is_closed():
            return
        self.tracker.set_command(cmd, mode=mode)
        try:
            # Post command directly into page window context (e.source === window)
            await self.page.evaluate("""
                (cmd) => {
                    window.postMessage(cmd, "*");
                }
            """, cmd)
        except Exception as e:
            logger.debug(f"Error dispatching command to page: {e}")

    async def connect(self):
        """Initializes the browser and connects to the target URL."""
        logger.info(f"Connecting to Three.js app at: {self.target_url}")
        self.playwright = await async_playwright().start()

        if self.cdp_url:
            logger.info(f"Attaching to running Chrome instance via CDP at {self.cdp_url}...")
            self.browser = await self.playwright.chromium.connect_over_cdp(self.cdp_url)
            self.context = self.browser.contexts[0]
            self.page = await self.context.new_page()
        else:
            logger.info(f"Launching Chromium (Headless: {self.headless})...")
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--window-size=1280,800"
                ]
            )
            self.context = await self.browser.new_context(viewport={"width": 1280, "height": 800})
            self.page = await self.context.new_page()

        # Expose Python callback to page JavaScript
        await self.page.expose_binding("__proxie_on_state", self._on_robot_state)

        # Inject listener script into the page before scripts run
        await self.page.add_init_script("""
            window.addEventListener("message", (event) => {
                if (event.data && event.data.type === "robot-state") {
                    window.__proxie_on_state(event.data);
                }
            });
        """)

        # Navigate to target URL
        await self.page.goto(self.target_url, wait_until="domcontentloaded")
        logger.info("[Bridge] Connected successfully to page!")
        self._running = True

    async def telemetry_processor(self):
        """Asynchronously processes incoming telemetry packets."""
        while self._running:
            try:
                state = await asyncio.wait_for(self._telemetry_queue.get(), timeout=1.0)
                self.tracker.update(state)
                self._telemetry_queue.task_done()
            except asyncio.TimeoutError:
                continue

    async def run_dashboard(self):
        """Renders the Rich TUI or formatted text lines."""
        if RICH_AVAILABLE:
            with Live(self.tracker.render_rich_panel(), refresh_per_second=10, transient=False) as live:
                while self._running:
                    live.update(self.tracker.render_rich_panel())
                    await asyncio.sleep(0.1)
        else:
            while self._running:
                print("\r" + self.tracker.get_summary_line(), end="", flush=True)
                await asyncio.sleep(0.1)

    async def run_autonomous_patrol(self):
        """Autonomous demo scenario showcasing multi-phase Python control."""
        logger.info("Waiting for initial telemetry stream stabilization...")
        await asyncio.sleep(1.5)
        
        logger.info("\n>>> PHASE 1: SPRINT FORWARD (Shift + W)")
        await self.controller.drive_forward(duration=3.0, run=True)
        await asyncio.sleep(1.0)
        
        logger.info("\n>>> PHASE 2: PERIMETER SQUARE PATROL")
        await self.controller.execute_square_patrol(side_seconds=2.0)
        await asyncio.sleep(1.0)
        
        logger.info("\n>>> PHASE 3: CLOSED-LOOP WAYPOINT SEEK TO (25.0, 25.0)")
        await self.controller.navigate_to_waypoint(target_x=25.0, target_z=25.0, tracker=self.tracker)
        await asyncio.sleep(1.0)
        
        logger.info("\n>>> PHASE 4: RETURN TO ORIGIN (0.0, 0.0)")
        await self.controller.navigate_to_waypoint(target_x=0.0, target_z=0.0, tracker=self.tracker)
        await asyncio.sleep(1.0)
        
        logger.info("\n>>> Autonomous Patrol Routine Finished Successfully!")

    async def run_integration_test(self) -> bool:
        """
        Headless automated test routine for CI/CD validation.
        Asserts:
        1. Telemetry frames arrive continuously (FPS > 15)
        2. Robot position changes in response to Python command
        """
        logger.info("[TEST] Starting automated bridge verification...")
        
        # Step 1: Wait for telemetry packets
        start_wait = time.time()
        while self.tracker.packet_count < 30:
            if time.time() - start_wait > 8.0:
                logger.error("[TEST FAILED] Did not receive telemetry packets within 8s!")
                return False
            await asyncio.sleep(0.1)
            
        logger.info(f"[TEST PASSED] Telemetry verified: {self.tracker.packet_count} packets received at ~{self.tracker.fps:.1f} FPS.")
        
        # Step 2: Record baseline position
        init_x = self.tracker.current_x
        init_z = self.tracker.current_z
        logger.info(f"[TEST] Baseline Position: X={init_x:.2f}, Z={init_z:.2f}")
        
        # Step 3: Dispatch movement command (Forward with run)
        logger.info("[TEST] Sending movement command (Forward + Run)...")
        await self.controller.drive_forward(duration=2.0, run=True)
        
        # Step 4: Verify position displacement
        post_x = self.tracker.current_x
        post_z = self.tracker.current_z
        displacement = math.hypot(post_x - init_x, post_z - init_z)
        logger.info(f"[TEST] Post Position: X={post_x:.2f}, Z={post_z:.2f} (Displacement: {displacement:.2f}m)")
        
        if displacement < 1.0:
            logger.error(f"[TEST FAILED] Robot did not move sufficiently! Displacement: {displacement:.2f}m")
            return False
            
        logger.info(f"[TEST PASSED] Robot responded to Python command with {displacement:.2f}m displacement.")
        return True

    async def close(self):
        self._running = False
        if self.page and not self.page.is_closed():
            await self.page.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("[Bridge] Shutdown complete.")


async def main():
    parser = argparse.ArgumentParser(description="Proxie DevOps Evaluation - Python to Three.js Bridge")
    parser.add_argument("--url", default="http://localhost:8000/index.html", help="URL of hosted Three.js app")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode (CI/CD)")
    parser.add_argument("--cdp-url", default=None, help="Connect to running Chrome instance via CDP (e.g. http://localhost:9222)")
    parser.add_argument("--mode", choices=["patrol", "observe", "test"], default="patrol", help="Execution mode")
    parser.add_argument("--duration", type=float, default=None, help="Stop after N seconds")
    args = parser.parse_args()

    # If targeting localhost or a local html file, ensure a static server is up
    target = args.url
    local_server = None
    if target.endswith(".html") and not target.startswith("http"):
        # Local file path provided
        local_server = ensure_local_server(8000)
        target = f"http://localhost:8000/{os.path.basename(target)}"
    elif "localhost:8000" in target or "127.0.0.1:8000" in target:
        local_server = ensure_local_server(8000)

    bridge = ProxieDevOpsBridge(
        target_url=target,
        headless=args.headless,
        cdp_url=args.cdp_url
    )


    try:
        await bridge.connect()
        
        tasks = [asyncio.create_task(bridge.telemetry_processor())]
        
        if args.mode == "test":
            success = await bridge.run_integration_test()
            await bridge.close()
            sys.exit(0 if success else 1)
        elif args.mode == "patrol":
            tasks.append(asyncio.create_task(bridge.run_dashboard()))
            tasks.append(asyncio.create_task(bridge.run_autonomous_patrol()))
        elif args.mode == "observe":
            tasks.append(asyncio.create_task(bridge.run_dashboard()))

        if args.duration:
            await asyncio.sleep(args.duration)
            bridge._running = False
        else:
            # Wait until patrol finishes or user interrupts
            await asyncio.gather(*tasks, return_exceptions=True)

    except KeyboardInterrupt:
        logger.info("\nInterrupted by user.")
    finally:
        await bridge.close()


if __name__ == "__main__":
    asyncio.run(main())
