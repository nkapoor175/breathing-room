"""Shared backend: relays every br/# MQTT message to the dashboard over a WebSocket.

Run:  uvicorn backend.app:app --port 8000 --reload
Docs: http://localhost:8000/docs
"""
import asyncio, json
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from common.bus import make_client, publish
from common.timeutil import now_iso

clients: set[asyncio.Queue] = set()   # one queue per connected browser
results: list[dict] = []              # Serverless Job results (in memory)
loop: asyncio.AbstractEventLoop | None = None
mq = None


def on_mqtt(client, userdata, msg):
    # Runs on paho's network thread: hand the message to the asyncio loop safely.
    try:
        data = json.loads(msg.payload)
    except json.JSONDecodeError:
        data = msg.payload.decode(errors="ignore")
    item = {"topic": msg.topic, "data": data}
    for q in list(clients):
        loop.call_soon_threadsafe(q.put_nowait, item)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global loop, mq
    loop = asyncio.get_running_loop()
    mq = make_client("backend-relay")
    mq.on_message = on_mqtt
    mq.on_connect = lambda c, u, f, rc, p: c.subscribe("br/#")   # re-subscribe after reconnects
    mq.loop_start()
    yield
    mq.loop_stop()
    mq.disconnect()


app = FastAPI(title="Breathing Room backend", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"ok": True, "ws_clients": len(clients), "results": len(results)}


@app.websocket("/ws")
async def ws(socket: WebSocket):
    """Every MQTT message as {"topic": ..., "data": ...}."""
    await socket.accept()
    q: asyncio.Queue = asyncio.Queue(maxsize=1000)
    clients.add(q)
    try:
        while True:
            await socket.send_json(await q.get())
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(q)


@app.post("/results")
async def post_results(body: dict):
    """Serverless Jobs (benchmarks, Nightmare Mode) POST their full results here."""
    body = {"received_at": now_iso(), **body}
    results.append(body)
    return {"ok": True, "n": len(results)}


@app.get("/results")
def get_results():
    return results


class OperatorReport(BaseModel):
    text: str
    zone: Optional[str] = None


@app.post("/operator/report")
def operator_report(r: OperatorReport):
    """Dashboard call-note form -> br/report_raw (Act's report fusion turns it into a Report)."""
    msg = {"t": now_iso(), "source": "call_note", "text": r.text, "zone": r.zone}
    publish(mq, "br/report_raw", msg)
    return {"ok": True, "published": msg}
