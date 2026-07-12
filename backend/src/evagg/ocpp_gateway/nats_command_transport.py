"""The real `CommandTransport` (Task 2.3's docstring: "real implementation
is NATS request-reply over `ocpp.cmd.{node_id}.{charger_id}`") — this is
that wiring, on the `ocpp-cmd.*` subject namespace rather than `ocpp.*` (see
`command_subject` for why).

Two independent halves, run on different nodes in general:

- `NatsCommandTransport`: the *sender* — wherever `RemoteCommandService`
  runs (`evagg.main`, behind the REST command endpoint), does a plain NATS
  request/reply and translates the result into a `CommandOutcome`. Never
  raises — a transport failure/timeout is itself an outcome
  (`CommandStatus.TIMED_OUT`/`REJECTED`), same as a charger declining.
- `serve_commands`: the *receiver* — runs once per OCPP gateway node,
  alongside that node's `LiveConnectionRegistry` (only that node has the
  actual open WebSockets), subscribes to every command addressed to it, and
  bridges each one onto the matching live connection's `send_call`.
"""

from __future__ import annotations

import json
import logging
import uuid

from evagg.ocpp_gateway.commands import CommandOutcome, CommandStatus
from evagg.ocpp_gateway.ws_app import LiveConnectionRegistry, RemoteCallRejected, RemoteCallTimeout

logger = logging.getLogger("evagg.ocpp_gateway.nats_command_transport")


def command_subject(node_id: str, charger_id: str) -> str:
    # Deliberately *not* under the `ocpp.>` prefix: that wildcard is the
    # `OCPP_EVENTS` JetStream stream's subject filter (see `event_bus.py`).
    # A command request is a plain core-NATS request/reply — but JetStream
    # auto-ACKs any published message matching a stream's subjects back to
    # its Reply-To subject, regardless of whether it was published via the
    # JS API. If this subject were `ocpp.cmd....`, that stream ACK would
    # race the real `serve_commands` reply for the same ephemeral inbox and
    # frequently win, so the sender would see a bogus rejection instead of
    # the actual outcome.
    return f"ocpp-cmd.{node_id}.{charger_id}"


class NatsCommandTransport:
    def __init__(self, nats_url: str) -> None:
        self._nats_url = nats_url
        self._nc = None

    async def connect(self) -> None:
        import nats

        self._nc = await nats.connect(self._nats_url)

    async def close(self) -> None:
        if self._nc is not None:
            await self._nc.close()

    async def send(
        self,
        node_id: str,
        charger_id: str,
        command_id: uuid.UUID,
        command_type: str,
        payload: dict,
        timeout_seconds: float,
    ) -> CommandOutcome:
        import nats.errors

        if self._nc is None:
            raise RuntimeError("NatsCommandTransport.connect() must be called before send()")

        request = json.dumps(
            {"command_id": str(command_id), "command_type": command_type, "payload": payload}
        ).encode()

        try:
            response = await self._nc.request(
                command_subject(node_id, charger_id), request, timeout=timeout_seconds
            )
        except nats.errors.TimeoutError:
            return CommandOutcome(
                status=CommandStatus.TIMED_OUT,
                result={"reason": "no response from the gateway node holding this charger's connection"},
            )
        except nats.errors.NoRespondersError:
            return CommandOutcome(
                status=CommandStatus.REJECTED,
                result={"reason": f"no gateway node is listening for charger {charger_id} (node {node_id})"},
            )

        try:
            body = json.loads(response.data)
        except ValueError:
            return CommandOutcome(status=CommandStatus.REJECTED, result={"reason": "malformed response from gateway node"})

        status_map = {
            "accepted": CommandStatus.ACCEPTED,
            "rejected": CommandStatus.REJECTED,
            "timed_out": CommandStatus.TIMED_OUT,
        }
        return CommandOutcome(status=status_map.get(body.get("status"), CommandStatus.REJECTED), result=body.get("result"))


async def serve_commands(nats_url: str, node_id: str, live_connections: LiveConnectionRegistry):
    """Runs for the lifetime of the app — call once at startup (see
    `evagg.edge_app`'s lifespan) and keep the returned connection object
    alive; there's nothing further to await, incoming requests are handled
    by the subscription callback."""
    import nats

    nc = await nats.connect(nats_url)

    async def _handle(msg) -> None:
        charger_id = msg.subject.rsplit(".", 1)[-1]
        try:
            request = json.loads(msg.data)
        except ValueError:
            await msg.respond(json.dumps({"status": "rejected", "result": {"reason": "malformed request"}}).encode())
            return

        connection = live_connections.get(charger_id)
        if connection is None:
            await msg.respond(
                json.dumps({"status": "rejected", "result": {"reason": "charger not connected on this node"}}).encode()
            )
            return

        command_type = request.get("command_type", "")
        payload = request.get("payload") or {}
        try:
            result = await connection.send_call(command_type, payload, timeout_seconds=25.0)
            await msg.respond(json.dumps({"status": "accepted", "result": result}).encode())
        except RemoteCallTimeout:
            await msg.respond(json.dumps({"status": "timed_out", "result": None}).encode())
        except RemoteCallRejected as exc:
            await msg.respond(
                json.dumps(
                    {"status": "rejected", "result": {"error_code": exc.error_code, "description": exc.description}}
                ).encode()
            )
        except Exception:  # noqa: BLE001 - a bad command payload must not kill the subscription
            logger.exception("unhandled error dispatching command to charger %s", charger_id)
            await msg.respond(json.dumps({"status": "rejected", "result": {"reason": "internal error"}}).encode())

    await nc.subscribe(f"ocpp-cmd.{node_id}.*", cb=_handle)
    return nc
