import os, json, ssl
import paho.mqtt.client as mqtt

def make_client(client_id: str) -> mqtt.Client:
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    c.username_pw_set(os.environ["MQTT_USER"], os.environ["MQTT_PASS"])
    c.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)
    c.connect(os.environ["MQTT_HOST"], int(os.environ.get("MQTT_PORT", 8883)))
    return c

def publish(c: mqtt.Client, topic: str, model_or_dict, retain: bool = False):
    """Returns paho's MQTTMessageInfo. A short script that exits right after publishing
    should call .wait_for_publish() on it, or the message may never leave.
    retain=True: the broker keeps the last message on this topic and hands it to anyone
    who subscribes later (e.g. the backend after a restart). Use for one-off state only."""
    data = model_or_dict.model_dump(by_alias=True) if hasattr(model_or_dict, "model_dump") else model_or_dict
    return c.publish(topic, json.dumps(data), qos=0, retain=retain)
