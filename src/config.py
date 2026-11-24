from dataclasses import dataclass

BROKER_HOST = "localhost"
BROKER_PORT = 1883
MQTT_TOPIC_PREFIX = "iot/telemetry"
MQTT_QOS = 1

# Sensor fleet & queue parameters
NUM_SENSORS = 4
BUFFER_CAPACITY = 100        # Max messages held per sensor during outage
MAX_AGE_SECONDS = 5.0        # Freshness threshold for Freshness-Aware queue

# Experimental matrix from proposal
OUTAGE_DURATIONS_SEC = [5, 15, 30]
MESSAGE_RATES_HZ = [1, 5, 10]
REPETITIONS = 5

# Phase timings (seconds)
PRE_OUTAGE_SEC = 5
POST_OUTAGE_SEC = 10

# Drain throttle on reconnect (messages/sec per sensor) to model constrained link
# and make queue-draining contention measurable on localhost
RECONNECT_DRAIN_RATE_HZ = 20.0


@dataclass
class RunConfig:
    strategy: str            # "fifo" or "freshness"
    outage_sec: int
    rate_hz: int
    rep: int
    num_sensors: int = NUM_SENSORS
    buffer_capacity: int = BUFFER_CAPACITY
    max_age_sec: float = MAX_AGE_SECONDS
    qos: int = MQTT_QOS