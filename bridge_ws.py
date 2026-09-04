"""
Proxie DevOps Evaluation - Extension WebSocket Bridge Daemon
Runs a local WebSocket server (ws://localhost:8765) that connects to the
Proxie Chrome Extension to observe live telemetry and dispatch robot commands.
"""

import asyncio
import json
import logging
import time
from typing import Set
import websockets

from telemetry_dashboard import TelemetryTracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("ProxieWS")

tracker = TelemetryTracker()
connected_clients: Set[websockets.WebSocketServerProtocol] = set()


async def broadcast_command(cmd_dict: dict, mode: str = "Active"):
    """Send a command dictionary to all connected browser extension tabs."""
    tracker.set_command(cmd_dict, mode=mode)
    payload = json.dumps(cmd_dict)
    if connected_clients:
        await asyncio.gather(*[client.send(payload) for client in connected_clients], return_exceptions=True)


async def handle_client(websocket):
    client_addr = websocket.remote_address
    logger.info(f"Browser extension connected from {client_addr}")
    connected_clients.add(websocket)
    
    try:
        async for message in websocket:
            try:
                packet = json.loads(message)
                if "data" in packet and packet["data"].get("type") == "robot-state":
                    tracker.update(packet["data"])
                    
                    # Print live line every 30 packets (~0.5 sec at 60fps)
                    if tracker.packet_count % 30 == 0:
                        print("\r" + tracker.get_summary_line(), end="", flush=True)
            except json.JSONDecodeError:
                pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients.remove(websocket)
        logger.info(f"\nBrowser extension disconnected from {client_addr}")


async def autonomous_patrol_routine():
    """
    Background demo task: Once a client connects, execute an autonomous
    patrol routine to demonstrate Python sending commands to the browser.
    """
    await asyncio.sleep(2)
    while True:
        if not connected_clients:
            await asyncio.sleep(1)
            continue
            
        logger.info("\n[Patrol] Commencing autonomous Python patrol routine...")
        
        # Step 1: Drive forward with run for 3 seconds
        await broadcast_command({
            "type": "robot-command",
            "forward": True, "back": False, "left": False, "right": False, "run": True
        }, mode="Patrol: Sprint Forward")
        await asyncio.sleep(3)
        
        # Step 2: Turn right while moving forward
        await broadcast_command({
            "type": "robot-command",
            "forward": True, "back": False, "left": False, "right": True, "run": False
        }, mode="Patrol: Right Arc Turn")
        await asyncio.sleep(2.5)
        
        # Step 3: Turn left while moving forward
        await broadcast_command({
            "type": "robot-command",
            "forward": True, "back": False, "left": True, "right": False, "run": False
        }, mode="Patrol: Left Arc Turn")
        await asyncio.sleep(2.5)
        
        # Step 4: Stop / Coast
        await broadcast_command({
            "type": "robot-command",
            "forward": False, "back": False, "left": False, "right": False, "run": False
        }, mode="Patrol: Idle/Coasting")
        await asyncio.sleep(2)


async def main(host: str = "0.0.0.0", port: int = 8765):
    logger.info("=" * 65)
    logger.info("  PROXIE ROBOT BRIDGE - EXTENSION WEBSOCKET DAEMON")
    logger.info(f"  Listening on ws://{host}:{port}")
    logger.info("  1. Load 'extension/' folder in Chrome (chrome://extensions)")
    logger.info("  2. Open the hosted Three.js page in Chrome")
    logger.info("=" * 65)
    
    server = await websockets.serve(handle_client, host, port)
    patrol_task = asyncio.create_task(autonomous_patrol_routine())
    
    try:
        await asyncio.Future()  # run forever
    except asyncio.CancelledError:
        pass
    finally:
        server.close()
        await server.wait_closed()
        patrol_task.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nWebSocket daemon stopped by user.")
