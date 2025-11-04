# NanoSense — Local IoT Telemetry Stack  
*(MQTT → Telegraf → InfluxDB → Grafana)*

A self-contained Docker-based system for collecting, storing, and visualizing sensor data locally.  
It supports any MQTT-capable device and includes an optional Python-based **emulator** for generating demo data.

---

## 📦 Architecture Overview

```
         ┌──────────────────────┐
         │  MQTT Emulator (opt) │
         │  BME688 / SPS30 / DP │
         └──────────┬───────────┘
                    │  MQTT
                    ▼
             ┌──────────────┐
             │  Mosquitto   │  ← MQTT Broker
             └──────────────┘
                    │
                    ▼
             ┌──────────────┐
             │   Telegraf   │  ← MQTT → InfluxDB bridge
             └──────────────┘
                    │
                    ▼
             ┌──────────────┐
             │   InfluxDB   │  ← Time-series database
             └──────────────┘
                    │
                    ▼
             ┌──────────────┐
             │   Grafana    │  ← Dashboards / Visualization
             └──────────────┘
```

---

## 🧰 Services Installed

- **Mosquitto** — MQTT broker
- **Telegraf** — MQTT→InfluxDB bridge & metric processing
- **InfluxDB 2.x** — time‑series database
- **Grafana** — dashboards & visualization
- *(optional)* **Python Emulator** — publishes demo data

---

## 🚀 Setup

### 1️⃣ Requirements

Windows Docker Desktop App

### 2️⃣ Clone & Start the Stack

```bash
git clone https://github.com/PatersonJQ/NanoSense.git
cd nanosense
-------- No Demo Data --------
docker compose up -d
--------Demo Date --------
docker compose --profile demo up -d
```

Check containers:
```bash
docker ps
```

Stop everything:
```bash
docker compose down
```

---

## 🌐 Access the Services

| Service    | URL                    | Login                  |
|-------------|------------------------|------------------------|
| Grafana     | http://localhost:3000  | admin / admin          |
| InfluxDB    | http://localhost:8086  | user / password1234    |
| Mosquitto   | tcp://localhost:1883   | anonymous              |

---

## ⚙️ Configuration Summary

### Mosquitto

Anonymous:
```
listener 1883
allow_anonymous true
```

### InfluxDB (from compose)
```
DOCKER_INFLUXDB_INIT_USERNAME=user
DOCKER_INFLUXDB_INIT_PASSWORD=password1234
DOCKER_INFLUXDB_INIT_ORG=some_org
DOCKER_INFLUXDB_INIT_BUCKET=some_data
DOCKER_INFLUXDB_INIT_ADMIN_TOKEN=4eYvsu8wZCJ6tKuE2sxvFHkvYFwSMVK0011hEEiojvejzpSaij86vYQomN_12au6eK-2MZ6Knr-Sax201y70w==
```

### Telegraf

Listens for topics like:
```
iot/+/+/+/telemetry/#
```

### Grafana

Provisioned from:
```
grafana-provisioning/datasources/
grafana-provisioning/dashboards/
```

---

## 🧪 Optional — Run the Emulator

The emulator publishes realistic telemetry (BME688 / SPS30 / DP) to MQTT.

### Create & activate venv
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Install
```bash
python3 -m pip install -r emulator/requirements.txt
```

### Run
```bash
python emulator/mqtt_emulator.py   --host 127.0.0.1 --port 1883   --site home1 --room lab   --devices pico2w-01,pico2w-02   --dp-channels 1,2   --interval 5
```

Use `--host mosquitto` if broker is in compose.

**Topics published**
```
iot/<site>/<room>/<device>/telemetry/bme688    # t_c,rh_pct,p_pa,gas_ohm,iaq,voc_index,co2_eq
iot/<site>/<room>/<device>/telemetry/sps30     # pm1_0,pm2_5,pm4_0,pm10
iot/<site>/<room>/<device>/telemetry/dp/<ch>   # dp_pa
iot/<site>/<room>/<device>/status              # retained
```
---

## 📊 Grafana Dashboards

Dashboards are auto-provisioned from:
```
grafana-provisioning/dashboards/
```
Recommended views:
- PM₂.₅ + ΔP dual-axis
- IAQ vs PM₂.₅ dual-axis
- VOC / CO₂eq trends
- Per-device tiles (temperature, humidity, status)
---

## 🧑‍💻 Development tips

Restart services after config changes:
```bash
docker compose restart telegraf
docker compose restart grafana
```
