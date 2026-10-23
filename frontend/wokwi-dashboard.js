
const WOKWI_API = "http://127.0.0.1:8000/latest-wokwi";

function addWokwiPanel() {
  if (document.getElementById("wokwiLivePanel")) return;

  const panel = document.createElement("section");
  panel.id = "wokwiLivePanel";

  panel.style.cssText = `
    margin: 24px 30px;
    padding: 24px;
    border: 1px solid #176b80;
    border-radius: 16px;
    background: #101e2b;
    color: #eef7ff;
    font-family: Arial, sans-serif;
  `;

  panel.innerHTML = `
    <h2 style="margin-top:0;color:#20d9ed">
      AGRISONIC · WOKWI LIVE LAB
    </h2>

    <p id="wokwiConnection">
      Connecting to FastAPI...
    </p>

    <div style="
      display:grid;
      grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
      gap:14px;
    ">
      <div class="wokwi-card">
        <small>SIMULATED SOUND</small>
        <h2 id="wokwiSound">--</h2>
        <p id="wokwiSoundRaw">Raw ADC: --</p>
      </div>

      <div class="wokwi-card">
        <small>SIMULATED VIBRATION</small>
        <h2 id="wokwiVibration">--</h2>
        <p id="wokwiVibrationRaw">Raw ADC: --</p>
      </div>

      <div class="wokwi-card">
        <small>FAULT SCENARIO</small>
        <h2 id="wokwiScenario">--</h2>
        <p id="wokwiDevice">Device: --</p>
      </div>

      <div class="wokwi-card">
        <small>BACKEND DETECTION</small>
        <h2 id="wokwiFault">--</h2>
        <p id="wokwiConfidence">Confidence: --</p>
        <p id="wokwiSeverity">Severity: --</p>
      </div>
    </div>

    <p id="wokwiUpdated" style="color:#a9c4d5">
      Waiting for the first ESP32 packet...
    </p>
  `;

  const style = document.createElement("style");

  style.textContent = `
    .wokwi-card {
      padding: 18px;
      background: #172a3a;
      border: 1px solid #315166;
      border-radius: 12px;
      overflow-wrap: anywhere;
    }

    .wokwi-card small {
      color: #9cc7d8;
      font-weight: bold;
    }

    .wokwi-card h2 {
      font-size: 24px;
      margin: 12px 0;
    }
  `;

  document.head.appendChild(style);
  document.body.prepend(panel);
}

function setWokwiText(id, value) {
  const element = document.getElementById(id);

  if (element) {
    element.textContent = value;
  }
}

async function refreshWokwiPanel() {
  try {
    const response = await fetch(WOKWI_API, {
      cache: "no-store"
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();

    if (!data.received || !data.inputs) {
      setWokwiText(
        "wokwiConnection",
        "WAITING · No Wokwi packet received yet"
      );
      return;
    }

    const input = data.inputs;
    const detection = data.detection || {};

    setWokwiText(
      "wokwiConnection",
      "CONNECTED TO FASTAPI · Latest packet received"
    );

    setWokwiText(
      "wokwiSound",
      input.sound_level == null
        ? "--"
        : Number(input.sound_level).toFixed(3)
    );

    setWokwiText(
      "wokwiVibration",
      input.vibration_level == null
        ? "--"
        : Number(input.vibration_level).toFixed(3)
    );

    setWokwiText(
      "wokwiSoundRaw",
      `Raw ADC: ${input.sound_raw ?? "--"}`
    );

    setWokwiText(
      "wokwiVibrationRaw",
      `Raw ADC: ${input.vibration_raw ?? "--"}`
    );

    setWokwiText(
      "wokwiScenario",
      input.scenario || "--"
    );

    setWokwiText(
      "wokwiDevice",
      `Device: ${data.device_id || input.device_id || "--"}`
    );

    setWokwiText(
      "wokwiFault",
      detection.fault || "Reading received"
    );

    setWokwiText(
      "wokwiConfidence",
      `Confidence: ${
        detection.confidence == null
          ? "--"
          : Number(detection.confidence).toFixed(2) + "%"
      }`
    );

    setWokwiText(
      "wokwiSeverity",
      `Severity: ${detection.severity || "--"}`
    );

    setWokwiText(
      "wokwiUpdated",
      `Packet #${data.request_id ?? "--"} · Received: ${
        data.received_at || "timestamp unavailable"
      }`
    );

  } catch (error) {
    setWokwiText(
      "wokwiConnection",
      `BACKEND UNAVAILABLE · ${error.message}`
    );
  }
}

function startWokwiDashboard() {
  addWokwiPanel();

  refreshWokwiPanel();

  // Refresh the latest readings every 2 seconds.
  setInterval(refreshWokwiPanel, 2000);
}

if (document.readyState === "loading") {
  document.addEventListener(
    "DOMContentLoaded",
    startWokwiDashboard,
    { once: true }
  );
} else {
  startWokwiDashboard();
}
