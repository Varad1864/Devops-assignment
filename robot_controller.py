"""
Proxie DevOps Evaluation - Robot Controller & Autopilot
Provides high-level commands, autonomous routines, and closed-loop waypoint navigation.
"""

import asyncio
import math
import logging
from typing import Callable, Awaitable, Optional, Dict, Any

logger = logging.getLogger("RobotController")


class RobotController:
    """
    High-level controller that translates motion intentions into
    Three.js 'robot-command' packets and sends them via the bridge.
    """

    def __init__(self, send_command_fn: Callable[[Dict[str, Any], Optional[str]], Awaitable[None]]):
        self.send_cmd = send_command_fn
        self._is_navigating = False

    async def stop(self):
        await self.send_cmd({
            "type": "robot-command",
            "forward": False, "back": False, "left": False, "right": False, "run": False
        }, mode="Idle (Stopped)")

    async def drive_forward(self, duration: float = 1.0, run: bool = False):
        await self.send_cmd({
            "type": "robot-command",
            "forward": True, "back": False, "left": False, "right": False, "run": run
        }, mode=f"Drive Forward ({'Run' if run else 'Walk'})")
        await asyncio.sleep(duration)
        await self.stop()

    async def drive_backward(self, duration: float = 1.0):
        await self.send_cmd({
            "type": "robot-command",
            "forward": False, "back": True, "left": False, "right": False, "run": False
        }, mode="Drive Reverse")
        await asyncio.sleep(duration)
        await self.stop()

    async def turn(self, direction: str = "right", duration: float = 1.0):
        is_left = direction.lower() == "left"
        await self.send_cmd({
            "type": "robot-command",
            "forward": False, "back": False, "left": is_left, "right": not is_left, "run": False
        }, mode=f"Turn {direction.capitalize()}")
        await asyncio.sleep(duration)
        await self.stop()

    async def execute_square_patrol(self, side_seconds: float = 2.5):
        """Drives the robot in a perimeter patrol square."""
        logger.info("[Patrol] Starting Square Perimeter Patrol...")
        for leg in range(4):
            # Drive straight
            await self.send_cmd({
                "type": "robot-command",
                "forward": True, "back": False, "left": False, "right": False, "run": True
            }, mode=f"Square Patrol (Leg {leg + 1}/4)")
            await asyncio.sleep(side_seconds)
            
            # Pivot 90 degrees right (at TURN_SPEED=2.5 rad/s, 90 deg = ~0.63s)
            await self.send_cmd({
                "type": "robot-command",
                "forward": False, "back": False, "left": False, "right": True, "run": False
            }, mode=f"Square Patrol (Pivot {leg + 1})")
            await asyncio.sleep(0.63)
            
        await self.stop()
        logger.info("[Patrol] Square Perimeter Patrol Complete.")

    async def execute_circular_patrol(self, duration: float = 6.0):
        """Drives the robot in a continuous smooth circle."""
        logger.info("[Patrol] Starting Circular Arc Patrol...")
        await self.send_cmd({
            "type": "robot-command",
            "forward": True, "back": False, "left": False, "right": True, "run": True
        }, mode="Circular Arc Patrol")
        await asyncio.sleep(duration)
        await self.stop()
        logger.info("[Patrol] Circular Arc Patrol Complete.")

    async def navigate_to_waypoint(self, target_x: float, target_z: float, tracker, tolerance: float = 3.0, timeout: float = 30.0):
        """
        Closed-loop proportional waypoint navigation:
        Uses real-time telemetry from Python tracker to steer robot toward (target_x, target_z).
        """
        logger.info(f"[Autopilot] Navigating to Waypoint ({target_x:.1f}, {target_z:.1f})...")
        self._is_navigating = True
        start_time = asyncio.get_event_loop().time()

        try:
            while self._is_navigating:
                if asyncio.get_event_loop().time() - start_time > timeout:
                    logger.warning(f"[Autopilot] Navigation timed out after {timeout}s")
                    break

                curr_x = tracker.current_x
                curr_z = tracker.current_z
                curr_rot = tracker.rotation_y

                dx = target_x - curr_x
                dz = target_z - curr_z
                distance = math.hypot(dx, dz)

                if distance <= tolerance:
                    logger.info(f"[Autopilot] Reached Waypoint! Margin: {distance:.2f}m")
                    break

                # Target angle in Three.js coordinates
                # In index.html:
                # x += Math.sin(rotation.y) * moved
                # z += Math.cos(rotation.y) * moved
                target_heading = math.atan2(dx, dz)

                # Angle error normalized to [-pi, pi]
                angle_error = (target_heading - curr_rot + math.pi) % (2 * math.pi) - math.pi

                # Decide steering
                turn_left = angle_error > 0.15
                turn_right = angle_error < -0.15
                drive_forward = abs(angle_error) < 1.2
                run_mode = distance > 15.0 and abs(angle_error) < 0.4

                await self.send_cmd({
                    "type": "robot-command",
                    "forward": drive_forward,
                    "back": False,
                    "left": turn_left,
                    "right": turn_right,
                    "run": run_mode
                }, mode=f"Seek ({target_x:.0f},{target_z:.0f}) Dist: {distance:.1f}m")

                await asyncio.sleep(0.05)  # 20 Hz control loop
        finally:
            self._is_navigating = False
            await self.stop()
