"""
Proxie DevOps Evaluation - Telemetry Dashboard
Renders real-time metrics (coordinates, FPS, speed, heading, distance) in a sleek terminal UI.
"""

import math
import time
from typing import Optional, Dict, Any

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.layout import Layout
    from rich.text import Text
    from rich.live import Live
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


def heading_to_cardinal(radians: float) -> str:
    deg = math.degrees(radians) % 360
    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    idx = round(deg / 45) % 8
    return f"{directions[idx]} ({deg:05.1f}°)"


class TelemetryTracker:
    def __init__(self):
        self.packet_count: int = 0
        self.start_time: float = time.time()
        self.last_packet_time: float = time.time()
        
        # Position & motion
        self.current_x: float = 0.0
        self.current_z: float = 0.0
        self.prev_x: float = 0.0
        self.prev_z: float = 0.0
        self.rotation_y: float = 0.0
        
        self.speed: float = 0.0
        self.total_distance: float = 0.0
        
        # FPS calculation
        self.fps: float = 0.0
        self.frame_times = []
        
        # Command state
        self.active_command: Dict[str, bool] = {
            "forward": False,
            "back": False,
            "left": False,
            "right": False,
            "run": False
        }
        self.current_mode: str = "Connected (Observing)"

    def update(self, state: Dict[str, Any]):
        now = time.time()
        dt = now - self.last_packet_time
        self.last_packet_time = now
        self.packet_count += 1
        
        # FPS calculation
        if dt > 0:
            instant_fps = 1.0 / dt
            self.frame_times.append(instant_fps)
            if len(self.frame_times) > 30:
                self.frame_times.pop(0)
            self.fps = sum(self.frame_times) / len(self.frame_times)
            
        x = float(state.get("x", 0.0))
        z = float(state.get("z", 0.0))
        rot = float(state.get("rotationY", 0.0))
        
        if self.packet_count > 1:
            dx = x - self.prev_x
            dz = z - self.prev_z
            dist = math.hypot(dx, dz)
            self.total_distance += dist
            if dt > 0:
                self.speed = dist / dt
        
        self.prev_x = self.current_x
        self.prev_z = self.current_z
        self.current_x = x
        self.current_z = z
        self.rotation_y = rot

    def set_command(self, cmd: Dict[str, bool], mode: Optional[str] = None):
        self.active_command = cmd
        if mode:
            self.current_mode = mode

    def get_summary_line(self) -> str:
        cardinal = heading_to_cardinal(self.rotation_y)
        return (
            f"[{self.current_mode}] "
            f"X: {self.current_x:6.2f} | Z: {self.current_z:6.2f} | "
            f"Heading: {cardinal:<11} | "
            f"Speed: {self.speed:4.1f} u/s | "
            f"FPS: {self.fps:5.1f} | "
            f"Packets: {self.packet_count}"
        )

    def render_rich_panel(self) -> Any:
        if not RICH_AVAILABLE:
            return self.get_summary_line()

        # Telemetry Table
        table = Table.grid(expand=True, padding=(0, 2))
        table.add_column("Metric", style="cyan bold", justify="left")
        table.add_column("Value", style="bright_white", justify="right")
        table.add_column("Metric", style="cyan bold", justify="left")
        table.add_column("Value", style="bright_white", justify="right")

        cardinal = heading_to_cardinal(self.rotation_y)
        dist_to_limit = 140.0 - max(abs(self.current_x), abs(self.current_z))
        
        # Format active control keys
        active_keys = []
        if self.active_command.get("forward"): active_keys.append("W (Fwd)")
        if self.active_command.get("back"): active_keys.append("S (Back)")
        if self.active_command.get("left"): active_keys.append("A (Left)")
        if self.active_command.get("right"): active_keys.append("D (Right)")
        if self.active_command.get("run"): active_keys.append("Shift (Run)")
        cmd_str = ", ".join(active_keys) if active_keys else "None (Coast)"

        table.add_row(
            "Position X", f"{self.current_x:7.2f} m",
            "FPS (Real-time)", f"{self.fps:6.1f} Hz"
        )
        table.add_row(
            "Position Z", f"{self.current_z:7.2f} m",
            "Speed", f"{self.speed:6.1f} m/s"
        )
        table.add_row(
            "Heading", cardinal,
            "Total Distance", f"{self.total_distance:6.1f} m"
        )
        table.add_row(
            "Boundary Margin", f"{dist_to_limit:6.1f} m",
            "Packets Recv", f"{self.packet_count}"
        )
        table.add_row(
            "Active Control", f"[green]{cmd_str}[/green]",
            "Bridge Status", f"[bold green]{self.current_mode}[/bold green]"
        )

        return Panel(
            table,
            title="[bold cyan]PROXIE ROBOT EXPLORER - REAL-TIME TELEMETRY BRIDGE[/bold cyan]",
            subtitle="[dim]Streaming continuously from live hosted Three.js scene via CDP[/dim]",
            border_style="cyan"
        )
