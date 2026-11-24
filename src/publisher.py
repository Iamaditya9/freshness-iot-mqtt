import json
import random
import threading
import time
from typing import Dict, Any
import paho.mqtt.client as mqtt

from config import (
    BROKER_HOST,
    BROKER_PORT,
    MQTT_TOPIC_PREFIX,
    PRE_OUTAGE_SEC,
    POST_OUTAGE_SEC,
    RECONNECT_DRAIN_RATE_HZ,
    RunConfig,
)
from queues import FIFOQueue, FreshnessAwareQueue


class SensorSimulator:
    def __init__(self, sensor_id: str, cfg: RunConfig, outage_flag: threading.Event):
        self.sensor_id = sensor_id
        self.cfg = cfg
        self.outage_flag = outage_flag

        if cfg.strategy == "fifo":
            self.queue = FIFOQueue(capacity=cfg.buffer_capacity)
        elif cfg.strategy == "freshness":
            self.queue = FreshnessAwareQueue(
                capacity=cfg.buffer_capacity,
                max_age_sec=cfg.max_age_sec,
            )
        else:
            raise ValueError(f"Unknown strategy: {cfg.strategy}")

        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"pub_{sensor_id}_{int(time.time() * 1000)}"
        )
        self.generated_count = 0
        self.published_count = 0
        self.total_tx_bytes = 0
        self._stop_event = threading.Event()
        self._q_lock = threading.Lock()

    def _generate_loop(self):
        interval = 1.0 / self.cfg.rate_hz
        seq = 0
        while not self._stop_event.is_set():
            seq += 1
            msg = {
                "sensor_id": self.sensor_id,
                "seq_num": seq,
                "gen_ts": time.time(),
                "payload": {
                    "temp_c": round(20.0 + random.uniform(-2.0, 5.0), 2),
                    "humidity": round(50.0 + random.uniform(-5.0, 5.0), 1),
                },
            }
            with self._q_lock:
                self.queue.push(msg)
                self.generated_count += 1
            time.sleep(interval)

    def _transmit_loop(self):
        drain_interval = 1.0 / RECONNECT_DRAIN_RATE_HZ
        topic = f"{MQTT_TOPIC_PREFIX}/{self.sensor_id}"
        while not self._stop_event.is_set():
            if self.outage_flag.is_set():
                time.sleep(0.05)
                continue

            with self._q_lock:
                msg = self.queue.pop(now=time.time())

            if msg is not None:
                raw = json.dumps(msg).encode("utf-8")
                self.client.publish(topic, raw, qos=self.cfg.qos)
                self.published_count += 1
                self.total_tx_bytes += len(raw)
                time.sleep(drain_interval)
            else:
                time.sleep(0.01)

    def run_for_schedule(self, total_duration: float):
        self.client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
        self.client.loop_start()

        gen_t = threading.Thread(target=self._generate_loop, daemon=True)
        tx_t = threading.Thread(target=self._transmit_loop, daemon=True)
        gen_t.start()
        tx_t.start()

        time.sleep(total_duration)
        self._stop_event.set()
        gen_t.join(timeout=1.0)
        tx_t.join(timeout=1.0)

        self.client.loop_stop()
        self.client.disconnect()

    def summary(self) -> Dict[str, Any]:
        q_stats = self.queue.stats()
        return {
            "sensor_id": self.sensor_id,
            "generated": self.generated_count,
            "published": self.published_count,
            "tx_bytes": self.total_tx_bytes,
            **q_stats,
        }