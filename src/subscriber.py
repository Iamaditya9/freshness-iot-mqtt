import json
import threading
import time
from typing import Dict, List, Set, Tuple
import paho.mqtt.client as mqtt

from config import BROKER_HOST, BROKER_PORT, MQTT_TOPIC_PREFIX, MQTT_QOS


class TelemetrySubscriber:
    def __init__(self, num_sensors: int, qos: int = MQTT_QOS):
        self.num_sensors = num_sensors
        self.qos = qos
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"sub_{int(time.time() * 1000)}"
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        self._lock = threading.Lock()
        self.received_records: List[Dict] = []
        self.seen_seqs: Dict[str, Set[int]] = {f"sensor_{i}": set() for i in range(num_sensors)}
        self.latest_gen_ts: Dict[str, float] = {}
        self.aoi_samples: List[Dict] = []
        self.total_rx_bytes = 0
        self.duplicate_count = 0

        self._stop_event = threading.Event()
        self._sampler_thread = threading.Thread(target=self._sample_aoi_loop, daemon=True)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        client.subscribe(f"{MQTT_TOPIC_PREFIX}/#", qos=self.qos)

    def _on_message(self, client, userdata, msg):
        recv_ts = time.time()
        raw_bytes = len(msg.payload)
        try:
            data = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return

        sensor_id = data["sensor_id"]
        seq_num = int(data["seq_num"])
        gen_ts = float(data["gen_ts"])
        e2e_delay = recv_ts - gen_ts

        with self._lock:
            self.total_rx_bytes += raw_bytes
            is_dup = seq_num in self.seen_seqs.setdefault(sensor_id, set())
            if is_dup:
                self.duplicate_count += 1
            else:
                self.seen_seqs[sensor_id].add(seq_num)

            # Update latest known generation timestamp for AoI tracking
            prev_ts = self.latest_gen_ts.get(sensor_id, 0.0)
            if gen_ts > prev_ts:
                self.latest_gen_ts[sensor_id] = gen_ts

            self.received_records.append({
                "sensor_id": sensor_id,
                "seq_num": seq_num,
                "gen_ts": gen_ts,
                "recv_ts": recv_ts,
                "e2e_delay": e2e_delay,
                "payload_bytes": raw_bytes,
                "is_duplicate": is_dup,
            })

    def _sample_aoi_loop(self):
        """Samples current Age of Information (now - latest_gen_ts) every 100ms."""
        while not self._stop_event.is_set():
            now = time.time()
            with self._lock:
                for sid, latest_ts in self.latest_gen_ts.items():
                    self.aoi_samples.append({
                        "sample_ts": now,
                        "sensor_id": sid,
                        "aoi_sec": max(0.0, now - latest_ts),
                    })
            time.sleep(0.1)

    def start(self):
        self.client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
        self.client.loop_start()
        self._sampler_thread.start()
        time.sleep(0.3)  # Allow subscription to settle

    def stop(self):
        self._stop_event.set()
        self._sampler_thread.join(timeout=1.0)
        self.client.loop_stop()
        self.client.disconnect()

    def compute_recovery_times(self, outage_end_ts: float) -> Dict[str, float]:
        """
        Time from connection restoration (outage_end_ts) until the receiver
        obtains the first reading generated AFTER the outage ended.
        """
        recovery: Dict[str, float] = {}
        with self._lock:
            for rec in self.received_records:
                sid = rec["sensor_id"]
                if sid not in recovery and rec["gen_ts"] >= outage_end_ts:
                    recovery[sid] = max(0.0, rec["recv_ts"] - outage_end_ts)
        return recovery