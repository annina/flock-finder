#!/usr/bin/env python3
import argparse
import time
import os
import psycopg2
import pyttsx4
import board
import digitalio
import adafruit_si4713
import serial  
from gps import gps, WATCH_ENABLE

from dotenv import load_dotenv
load_dotenv()


#---
# text to speech init 
#---

engine = pyttsx4.init()

# =============================================================================
# CONFIGURATION (Change your settings here)
# =============================================================================

# 1. Radius Settings
SEARCH_RADIUS_METERS = 75.0 

# 2. Database Settings
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PW")
}

# 3. Hardware & Timing Settings
FM_FREQUENCY_KHZ = 103500    # 103.5 MHz
DB_CHECK_INTERVAL = 5        # Check database every 5 seconds
ALERT_COOLDOWN_SEC = 300     # Don't alert for the same camera ID within 5 minutes

# 4. Serial Settings (Feather M4)
# Note: Check your actual port by running `ls /dev/tty*` in the Pi terminal. 
# Feather boards typically show up as /dev/ttyACM0 or /dev/ttyUSB0.
SERIAL_PORT = "/dev/ttyACM0" 
BAUD_RATE = 9600

# =============================================================================
# SQL DEFINITION
# =============================================================================

SQL = """
SELECT 
    osm_type, 
    osm_id, 
    ST_AsText(geom) AS geom_wkt, 
    camera_type, 
    operator_name 
FROM osm_surveillance_elements
WHERE ST_DWithin(
    geom::geography, 
    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, 
    %s
);
"""

# Track alerted cameras to prevent spamming {osm_id: timestamp_of_alert}
alerted_cameras = {}

# Track the current state of the matrix display so we don't spam the serial port
display_is_active = False 

# =============================================================================
# HARDWARE & AUDIO SETUP
# =============================================================================

def init_serial():
    """Initializes the USB Serial connection to the Feather M4."""
    print(f"Connecting to matrix controller on {SERIAL_PORT}...")
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2) # Give the Arduino a moment to reset upon connection
        print("✓ Matrix controller connected")
        return ser
    except serial.SerialException as e:
        print(f"Failed to connect to Matrix on {SERIAL_PORT}: {e}")
        print("Continuing without visual matrix display...")
        return None

def init_fm_transmitter():
    """Initializes the Adafruit SI4713 FM Transmitter."""
    print("Initializing SI4713 FM transmitter...")
    try:
        i2c = board.I2C()
        si_reset = digitalio.DigitalInOut(board.D5)
        si4713 = adafruit_si4713.SI4713(i2c, reset=si_reset, timeout_s=0.5)
        
        si4713.tx_frequency_khz = FM_FREQUENCY_KHZ
        si4713.tx_power = 115
        si4713.configure_rds(0xADAF, station=b"ALPR-WARN", rds_buffer=b"Live Camera Tracker")
        si4713.gpio_control(gpio1=True, gpio2=True)
        
        print(f"✓ Transmitting on {si4713.tx_frequency_khz / 1000.0:0.3f} MHz")
        return si4713
    except Exception as e:
        print(f"Failed to initialize FM transmitter hardware: {e}")
        print("Continuing in DB-only log mode (No FM Audio)...")
        return None

def broadcast_alert(message, transmitter):
    """Uses pyttsx3 to speak the alert message over the audio channel."""
    print(f"📢 AUDIO ALERT: {message}")
    
    if transmitter:
        transmitter.gpio_set(gpio1=True, gpio2=False)
        
    global engine
    engine.setProperty('volume', 1.0)
    engine.say(message)
    engine.runAndWait()
    
    if transmitter:
        transmitter.gpio_set(gpio1=False, gpio2=True)

# =============================================================================
# CORE SEARCH LOGIC
# =============================================================================

def check_nearby_cameras(lat, lon, radius, transmitter, ser_conn):
    """Queries PostGIS for nearby cameras, handles serial display, and audio cooldowns."""
    global display_is_active
    current_time = time.time()
    
    # Clean up expired cooldowns
    expired = [osm_id for osm_id, timestamp in alerted_cameras.items() if current_time - timestamp > ALERT_COOLDOWN_SEC]
    for osm_id in expired:
        del alerted_cameras[osm_id]

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute(SQL, (lon, lat, radius))
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except psycopg2.Error as e:
        print(f"Database Query Error: {e}")
        return

    # --- SERIAL MATRIX LOGIC ---
    if not rows:
        # No cameras found in radius. Turn OFF display if it is currently on.
        if display_is_active:
            if ser_conn:
                ser_conn.write(b'0')
            print("[Matrix] Sending STOP command (0). Out of range.")
            display_is_active = False
        return

    # Cameras ARE in radius. Turn ON display if it is currently off.
    if not display_is_active:
        if ser_conn:
            ser_conn.write(b'1')
        print("[Matrix] Sending START command (1). Targets acquired.")
        display_is_active = True

    # --- AUDIO ALERT LOGIC ---
    for r in rows:
        osm_type, osm_id, geom_wkt, camera_type, operator_name = r
        
        # Skip if we already alerted via audio recently
        if osm_id in alerted_cameras:
            continue
            
        print(f"\n[!] CAMERA DETECTED IN RADIUS: {osm_type} {osm_id}")
        print(f"    Type: {camera_type} | Operator: {operator_name}")
        
        alerted_cameras[osm_id] = current_time
        
        alert_msg = "Warning. Surveillance camera detected ahead. whaaaaaaa whaaaaa whaaaa"
        broadcast_alert(alert_msg, transmitter)

# =============================================================================
# MAIN RUN LOOP
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Continuous GPS PostGIS Surveillance Scanner")
    parser.add_argument("--radius", type=float, default=SEARCH_RADIUS_METERS, 
                        help=f"Search radius in meters (default from script configuration: {SEARCH_RADIUS_METERS}m)")
    args = parser.parse_args()

    # Initialize Hardware
    transmitter = init_fm_transmitter()
    ser_conn = init_serial()

    # Connect to local gpsd daemon
    print("Connecting to gpsd...")
    session = gps(mode=WATCH_ENABLE)
    
    last_db_check = 0
    current_lat = None
    current_lon = None

    print(f"\nTracking active with search radius: {args.radius} meters.")
    print("Press Ctrl+C to stop.")
    print("-" * 50)

    try:
        while True:
            report = session.next()
            print(f"checking gpsd")
            if report['class'] == 'TPV':
                mode = getattr(report, 'mode', 0)
                if mode >= 2:
                    current_lat = getattr(report, 'lat', 0.0)
                    current_lon = getattr(report, 'lon', 0.0)
                    speed = getattr(report, 'spd', 0.0)
                    print(f"🛰️ Live Fix | Lat: {current_lat:.6f} | Lon: {current_lon:.6f} | Speed: {speed:.1f} m/s", end="\r")
                else:
                    print("🛰️ Waiting for satellite lock...", end="\r")
                    current_lat, current_lon = None, None

            now = time.time()
            if now - last_db_check >= DB_CHECK_INTERVAL:
                last_db_check = now
                
                if current_lat and current_lon:
                    check_nearby_cameras(current_lat, current_lon, args.radius, transmitter, ser_conn)

    except KeyboardInterrupt:
        print("\nShutting down tracking script cleanly.")
    finally:
        # Clean shutdown for hardware
        if transmitter:
            transmitter.gpio_set(gpio1=False, gpio2=False)
        if ser_conn:
            ser_conn.write(b'0') # Ensure display turns off when script exits
            ser_conn.close()

if __name__ == "__main__":
    main()
