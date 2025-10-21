
#!/usr/bin/env python3
import argparse
import json
import random
import signal
import time
from datetime import datetime, timezone
from typing import List

import paho.mqtt.client as mqtt


def rfc3339_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


class RandomWalk:
    def __init__(self, start: float, step: float, lo: float, hi: float):
        self.v = start
        self.step = step
        self.lo = lo
        self.hi = hi

    def next(self, jitter: float = 0.5) -> float:
        self.v += random.uniform(-self.step, self.step)
        self.v += random.gauss(0, jitter) * 0.01 * (self.hi - self.lo)
        self.v = clamp(self.v, self.lo, self.hi)
        return self.v


class DeviceEmulator:
    def __init__(self, client: mqtt.Client, site: str, room: str, device: str, interval: float, qos: int, dp_channels: List[int]):
        self.client = client
        self.site = site
        self.room = room
        self.device = device
        self.interval = interval
        self.qos = qos
        self.dp_channels = dp_channels

        self.temp = RandomWalk(start=random.uniform(18, 23), step=0.05, lo=10, hi=35)
        self.rh = RandomWalk(start=random.uniform(35, 55), step=0.2, lo=15, hi=90)
        self.press_pa = RandomWalk(start=101325, step=30, lo=98000, hi=104000)
        self.gas = RandomWalk(start=50000, step=500, lo=1000, hi=200000)

        # New: “smart” signals from BSEC-style outputs
        self.iaq = RandomWalk(start=35.0, step=2.5, lo=5.0, hi=250.0)         # 0..500 index (we cap to 250 in emu)
        self.voc_index = RandomWalk(start=15.0, step=2.0, lo=0.0, hi=500.0)   # 0..500 index
        self.co2_eq = RandomWalk(start=600.0, step=15.0, lo=400.0, hi=2000.0) # ppm

        self.pm1 = RandomWalk(start=3, step=0.5, lo=0, hi=100)
        self.pm25 = RandomWalk(start=6, step=0.8, lo=0, hi=200)
        self.pm4 = RandomWalk(start=8, step=1.0, lo=0, hi=250)
        self.pm10 = RandomWalk(start=10, step=1.2, lo=0, hi=300)

        # Differential pressure per channel
        # Make channel 1 ≈ HEPA ~ -80 Pa, channel 2 ≈ WAFER ~ -95 Pa (negative drop convention)
        self.dp_walk = {}
        for ch in dp_channels:
            base = -80.0 if ch == 1 else -95.0
            self.dp_walk[ch] = RandomWalk(start=base + random.uniform(-8, 8), step=3.0, lo=-300, hi=20)

    @property
    def base(self) -> str:
        return f"iot/{self.site}/{self.room}/{self.device}"

    def topic_bme(self) -> str:
        return f"{self.base}/telemetry/bme688"

    def topic_sps(self) -> str:
        return f"{self.base}/telemetry/sps30"

    def topic_dp(self, ch: int) -> str:
        return f"{self.base}/telemetry/dp/{ch}"

    def topic_status(self) -> str:
        return f"{self.base}/status"

    def publish_status(self, online: bool):
        payload = {
            "online": online,
            "fw": "emu-1.1.0",
            "rssi_dbm": random.randint(-70, -45),
            "ts": rfc3339_now(),
        }
        self.client.publish(self.topic_status(), json.dumps(payload), qos=self.qos, retain=True)

    def _bme_payload(self, ts: str) -> dict:
        # Base env
        t_c = round(self.temp.next(), 2)
        rh = round(self.rh.next(), 1)
        p_pa = round(self.press_pa.next(), 0)
        gas = round(self.gas.next(), 0)

        # Light coupling: IAQ/VOC can spike occasionally
        iaq_val = self.iaq.next()
        if random.random() < 0.02:
            iaq_val = clamp(iaq_val + random.uniform(20, 80), 5.0, 250.0)
        voc_val = clamp(self.voc_index.next() + random.uniform(-3, 3) + 0.3 * (iaq_val - 35.0), 0.0, 500.0)
        co2_val = self.co2_eq.next()
        if random.random() < 0.02:
            co2_val = clamp(co2_val + random.uniform(100, 300), 400.0, 2000.0)

        return {
            "t_c": t_c,
            "rh_pct": rh,
            "p_pa": p_pa,
            "gas_ohm": gas,
            "iaq": round(iaq_val, 1),
            "voc_index": round(voc_val, 1),
            "co2_eq": round(co2_val, 0),
            "ts": ts,
        }

    def _sps_payload(self, ts: str) -> dict:
        # Occasional PM event
        if random.random() < 0.015:
            bump = random.uniform(10, 30)
            self.pm25.v = clamp(self.pm25.v + bump, 0, 200)
            self.pm10.v = clamp(self.pm10.v + bump * 1.2, 0, 300)
        return {
            "pm1_0": round(self.pm1.next(), 1),
            "pm2_5": round(self.pm25.next(), 1),
            "pm4_0": round(self.pm4.next(), 1),
            "pm10": round(self.pm10.next(), 1),
            "ts": ts,
        }

    def _dp_payload(self, ch: int, ts: str) -> dict:
        return {"dp_pa": round(self.dp_walk[ch].next(), 1), "ts": ts}

    def publish_once(self):
        ts = rfc3339_now()

        # BME688 (now includes iaq, voc_index, co2_eq)
        self.client.publish(self.topic_bme(), json.dumps(self._bme_payload(ts)), qos=self.qos, retain=False)

        # SPS30
        self.client.publish(self.topic_sps(), json.dumps(self._sps_payload(ts)), qos=self.qos, retain=False)

        # Differential pressure (per channel)
        for ch in self.dp_channels:
            self.client.publish(self.topic_dp(ch), json.dumps(self._dp_payload(ch, ts)), qos=self.qos, retain=False)



def on_connect(client, userdata, flags, rc, properties=None):
    print("Connected to broker." if rc == 0 else f"Connection failed: rc={rc}")


def build_client(client_id: str, host: str, port: int, keepalive: int, username: str = None, password: str = None) -> mqtt.Client:
    client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv5, transport="tcp")
    if username or password:
        client.username_pw_set(username=username, password=password)
    client.on_connect = on_connect
    client.connect(host, port, keepalive=keepalive)
    client.loop_start()
    return client


def parse_args():
    p = argparse.ArgumentParser(description="MQTT IoT Emulator (subtopics per sensor)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--qos", type=int, default=0, choices=[0,1])
    p.add_argument("--keepalive", type=int, default=30)
    p.add_argument("--username", default=None)
    p.add_argument("--password", default=None)
    p.add_argument("--site", default="home1")
    p.add_argument("--room", default="lab")
    p.add_argument("--devices", default="pico2w-01")
    p.add_argument("--dp-channels", default="1,2")
    p.add_argument("--interval", type=float, default=5.0)
    return p.parse_args()


def main():
    args = parse_args()
    client = build_client("emulator", args.host, args.port, args.keepalive, args.username, args.password)
    devices = [d.strip() for d in args.devices.split(",") if d.strip()]
    dp_channels = [int(x) for x in args.dp_channels.split(",") if x.strip()]

    # create emulators and set online
    emus: List[DeviceEmulator] = [DeviceEmulator(client, args.site, args.room, dev, args.interval, args.qos, dp_channels) for dev in devices]
    for emu in emus:
        emu.publish_status(True)

    print(f"Publishing every {args.interval}s to mqtt://{args.host}:{args.port} for devices: {', '.join(devices)}")
    print("Topics: .../telemetry/bme688, .../telemetry/sps30, .../telemetry/dp/<channel> ; status retained. Ctrl+C to stop.")

    stop = {"flag": False}
    def handle_sig(sig, frame):
        stop["flag"] = True
    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    try:
        while not stop["flag"]:
            start = time.time()
            for emu in emus:
                emu.publish_once()
            sleep = args.interval - (time.time() - start)
            if sleep > 0:
                time.sleep(sleep)
    finally:
        for emu in emus:
            emu.publish_status(False)
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
