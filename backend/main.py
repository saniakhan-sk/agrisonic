
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Literal
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
import os
import logging
from threading import Lock
from twilio.rest import Client

from signal_generator import generate_signals
from signal_processing import (
    extract_features,
    filter_signal,
    calculate_fft
)


# ---------------------------------
# FastAPI Configuration
# ---------------------------------

app = FastAPI(
    title="AgriSonic Acoustic Fault Detection",
    description="Pump fault detection and Wokwi sensor simulation API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# ---------------------------------
# Load Trained ML Model
# ---------------------------------

model = joblib.load("model.pkl")


# ---------------------------------
# Critical Alert Configuration
# ---------------------------------

logger = logging.getLogger(__name__)

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
ALERT_TO_PHONE = os.getenv("ALERT_TO_PHONE")

alert_lock = Lock()
critical_alert_active = False


def send_critical_sms(fault, location, confidence):
    """Send an SMS when a critical motor fault is detected."""

    if not all([
        TWILIO_ACCOUNT_SID,
        TWILIO_AUTH_TOKEN,
        TWILIO_PHONE_NUMBER,
        ALERT_TO_PHONE
    ]):
        logger.error(
            "SMS not sent: Twilio configuration is missing."
        )
        return

    try:
        client = Client(
            TWILIO_ACCOUNT_SID,
            TWILIO_AUTH_TOKEN
        )

        message = client.messages.create(
            body=(
                "URGENT AGRISONIC ALERT: Critical motor fault detected. "
                f"Fault: {fault}. "
                f"Location: {location}. "
                f"Model confidence: {confidence}%. "
                "Inspect the motor immediately and follow "
                "site safety procedures."
            ),
            from_=TWILIO_PHONE_NUMBER,
            to=ALERT_TO_PHONE
        )

        logger.info(
            "Critical SMS submitted. Message SID: %s",
            message.sid
        )

    except Exception:
        logger.exception("Failed to send critical SMS.")


# ---------------------------------
# Shared Fault Detection Function
# ---------------------------------

def run_detection(fault: str, send_alert: bool = True):
    """
    Run the existing simulated signal-generation and ML pipeline.

    NOTE:
    The fault argument selects a simulated operating condition.
    This function does not yet classify the Wokwi potentiometer
    readings directly.
    """

    global critical_alert_active

    allowed_faults = {
        "normal",
        "imbalance",
        "misalignment",
        "loose_mounting"
    }

    if fault not in allowed_faults:
        fault = "normal"

    rpm_values = {
        "normal": 1500,
        "imbalance": 1450,
        "misalignment": 1480,
        "loose_mounting": 1400
    }

    rpm = rpm_values[fault]
    fs = 2000

    t, acoustic, sensors = generate_signals(
        fault=fault,
        rpm=rpm,
        fs=fs
    )

    features = []

    # Extract acoustic features
    acoustic_features = extract_features(
        acoustic,
        fs
    )

    features.extend([
        acoustic_features["rms"],
        acoustic_features["peak"],
        acoustic_features["dominant_frequency"]
    ])

    sensor_rms = []
    filtered_sensors = []

    # Extract features from the four simulated sensor signals
    for i in range(4):

        sensor_features = extract_features(
            sensors[i],
            fs
        )

        features.extend([
            sensor_features["rms"],
            sensor_features["peak"],
            sensor_features["dominant_frequency"]
        ])

        sensor_rms.append(
            sensor_features["rms"]
        )

        filtered_sensors.append(
            filter_signal(sensors[i], fs)
        )

    feature_names = [
        "acoustic_rms",
        "acoustic_peak",
        "acoustic_frequency",
        "s1_rms",
        "s1_peak",
        "s1_frequency",
        "s2_rms",
        "s2_peak",
        "s2_frequency",
        "s3_rms",
        "s3_peak",
        "s3_frequency",
        "s4_rms",
        "s4_peak",
        "s4_frequency"
    ]

    input_data = pd.DataFrame(
        [features],
        columns=feature_names
    )

    # ML prediction
    prediction = model.predict(input_data)[0]

    if not hasattr(model, "predict_proba"):
        raise RuntimeError(
            "The loaded model does not support predict_proba()."
        )

    probabilities = model.predict_proba(input_data)[0]
    confidence = float(max(probabilities) * 100)

    strongest_sensor = int(np.argmax(sensor_rms))

    selected_signal = filtered_sensors[strongest_sensor]

    # FFT
    frequencies, magnitude = calculate_fft(
        selected_signal,
        fs
    )

    waveform_length = min(500, len(selected_signal))

    waveform_indices = np.linspace(
        0,
        len(selected_signal) - 1,
        waveform_length
    ).astype(int)

    waveform = selected_signal[waveform_indices]

    fft_limit = 200
    frequencies = frequencies[:fft_limit]
    magnitude = magnitude[:fft_limit]

    # Severity rules
    if prediction == "normal":
        severity = "Normal"
        status = "RUNNING"

    elif prediction == "loose_mounting":
        severity = "Critical"
        status = "SAFE STOP"

    else:
        severity = "Warning"
        status = "RUNNING"

    # Critical alert episode handling
    if send_alert:
        with alert_lock:

            if severity == "Critical" and not critical_alert_active:
                critical_alert_active = True

                # The caller schedules the SMS through BackgroundTasks.
                # This placeholder is replaced by the route-specific
                # scheduling function below.

            elif severity != "Critical":
                critical_alert_active = False

    return {
        "fault": str(prediction),
        "confidence": round(confidence, 2),
        "location": f"Sensor {strongest_sensor + 1}",
        "severity": severity,
        "status": status,
        "sensor_rms": sensor_rms,
        "rpm": rpm,
        "waveform": waveform.tolist(),
        "frequency": frequencies.tolist(),
        "spectrum": magnitude.tolist()
    }


# ---------------------------------
# Home Route
# ---------------------------------

@app.get("/")
def home():
    return {
        "message": "AgriSonic backend running",
        "docs": "/docs",
        "wokwi_receive": "/wokwi-demo",
        "wokwi_latest": "/latest-wokwi"
    }


# ---------------------------------
# Original Fault Detection Route
# ---------------------------------

@app.get("/detect/{fault}")
def detect_fault(
    fault: str,
    background_tasks: BackgroundTasks
):
    global critical_alert_active

    result = run_detection(fault, send_alert=False)

    # Preserve the existing critical SMS behaviour.
    with alert_lock:

        if (
            result["severity"] == "Critical"
            and not critical_alert_active
        ):
            critical_alert_active = True

            background_tasks.add_task(
                send_critical_sms,
                result["fault"],
                result["location"],
                result["confidence"]
            )

        elif result["severity"] != "Critical":
            critical_alert_active = False

    return result


# ---------------------------------
# Wokwi ESP32 Request Schema
# ---------------------------------

class WokwiReading(BaseModel):
    device_id: str

    scenario: Literal[
        "normal",
        "imbalance",
        "misalignment",
        "loose_mounting"
    ]

    sound_raw: int
    vibration_raw: int
    sound_level: float
    vibration_level: float


# Latest Wokwi reading (in-memory demo storage)
latest_wokwi_data = {}
wokwi_request_number = 0


# ---------------------------------
# Receive Simulated ESP32 Data
# ---------------------------------

@app.post("/wokwi-demo")
def receive_wokwi_data(data: WokwiReading):

    global latest_wokwi_data, wokwi_request_number

    # Run the existing ML pipeline using the selected
    # simulated scenario, without sending real SMS messages.
    detection = run_detection(
        data.scenario,
        send_alert=False
    )

    wokwi_request_number += 1

    latest_wokwi_data = {
        "request_id": wokwi_request_number,
        "received_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "device_id": data.device_id,
        "inputs": data.model_dump(),
        "detection": detection
    }

    logger.info(
        "Received Wokwi data from %s",
        data.device_id
    )

    return {
        "message": "AgriSonic Wokwi data received",
        "request_id": wokwi_request_number,
        "fault": detection["fault"],
        "severity": detection["severity"]
    }


# ---------------------------------
# Get Latest Wokwi Data
# ---------------------------------

@app.get("/latest-wokwi")
def get_latest_wokwi_data():

    if not latest_wokwi_data:
        return {
            "received": False,
            "message": "Waiting for Wokwi sensor data"
        }

    return {
        "received": True,
        **latest_wokwi_data
    }
