// Proxie Robot Bridge - Content Script
// Bridges window.postMessage to a local Python WebSocket daemon (ws://localhost:8765)

(function () {
  console.log("[Proxie Bridge] Content script initialized on:", window.location.href);

  let ws = null;
  let isConnected = false;
  let statePacketCount = 0;
  let commandPacketCount = 0;
  let reconnectTimer = null;

  // Floating Status HUD
  const hud = document.createElement("div");
  hud.id = "proxie-bridge-hud";
  hud.style.position = "fixed";
  hud.style.top = "10px";
  hud.style.right = "10px";
  hud.style.padding = "8px 14px";
  hud.style.background = "rgba(18, 24, 38, 0.85)";
  hud.style.border = "1px solid rgba(0, 229, 255, 0.3)";
  hud.style.borderRadius = "8px";
  hud.style.color = "#fff";
  hud.style.fontFamily = "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace";
  hud.style.fontSize = "12px";
  hud.style.zIndex = "999999";
  hud.style.backdropFilter = "blur(6px)";
  hud.style.boxShadow = "0 4px 12px rgba(0, 0, 0, 0.3)";
  hud.style.pointerEvents = "none";
  hud.style.transition = "all 0.3s ease";
  hud.innerHTML = `
    <div style="display: flex; align-items: center; gap: 8px;">
      <span id="bridge-dot" style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#ff5252;"></span>
      <strong style="color: #00e5ff;">PROXIE BRIDGE</strong>
      <span id="bridge-status" style="color: #bbb;">Connecting...</span>
    </div>
    <div id="bridge-metrics" style="margin-top: 4px; font-size: 11px; color: #888;">
      TX: 0 | RX: 0
    </div>
  `;
  document.body.appendChild(hud);

  function updateHUD(status, color, text) {
    const dot = document.getElementById("bridge-dot");
    const statusEl = document.getElementById("bridge-status");
    const metricsEl = document.getElementById("bridge-metrics");
    if (dot) dot.style.background = color;
    if (statusEl) {
      statusEl.textContent = text;
      statusEl.style.color = color;
    }
    if (metricsEl) {
      metricsEl.textContent = `Telemetry TX: ${statePacketCount} | Commands RX: ${commandPacketCount}`;
    }
  }

  function connectWebSocket() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    try {
      ws = new WebSocket("ws://localhost:8765");

      ws.onopen = () => {
        isConnected = true;
        console.log("[Proxie Bridge] Connected to local Python WebSocket daemon at ws://localhost:8765");
        updateHUD("connected", "#00e676", "Connected (Python)");
        if (reconnectTimer) {
          clearTimeout(reconnectTimer);
          reconnectTimer = null;
        }
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          if (message && message.type === "robot-command") {
            commandPacketCount++;
            // Post command directly into the page window context
            window.postMessage(message, "*");
            updateHUD("connected", "#00e676", "Active");
          }
        } catch (err) {
          console.error("[Proxie Bridge] Error parsing incoming WebSocket command:", err);
        }
      };

      ws.onclose = () => {
        isConnected = false;
        updateHUD("disconnected", "#ff5252", "Disconnected (reconnecting...)");
        scheduleReconnect();
      };

      ws.onerror = () => {
        isConnected = false;
        ws.close();
      };
    } catch (e) {
      console.warn("[Proxie Bridge] WebSocket connection attempt failed:", e);
      scheduleReconnect();
    }
  }

  function scheduleReconnect() {
    if (!reconnectTimer) {
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        connectWebSocket();
      }, 2000);
    }
  }

  // Listen for Three.js robot-state broadcasts from the page
  window.addEventListener("message", (event) => {
    // Only capture robot-state from the current window
    if (event.source !== window || !event.data || event.data.type !== "robot-state") return;

    statePacketCount++;

    // Forward telemetry over WebSocket to Python if connected
    if (ws && ws.readyState === WebSocket.OPEN) {
      const payload = JSON.stringify({
        source: "proxie-extension",
        timestamp: performance.now(),
        data: event.data,
      });
      ws.send(payload);
    }

    // Update HUD metrics periodically
    if (statePacketCount % 30 === 0) {
      const metricsEl = document.getElementById("bridge-metrics");
      if (metricsEl) {
        metricsEl.textContent = `Telemetry TX: ${statePacketCount} | Commands RX: ${commandPacketCount}`;
      }
    }
  });

  // Initial connection
  connectWebSocket();
})();
