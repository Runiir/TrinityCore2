"""Serve the isolated build-60895 login adapter on loopback only."""
import asyncio
import ssl
import threading

from tools.client_compatibility.lab_runtime import ROOT, connection
from . import accounts, rest
from .events import event
from .rpc import Session


async def main():
    connection().close()
    accounts.migrate()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(ROOT / "config/bnetserver.cert.pem", ROOT / "secrets/bnetserver.key.pem")
    http = rest.server()
    threading.Thread(target=http.serve_forever, daemon=True).start()

    async def client(reader, writer):
        await Session(reader, writer).run()

    listener = await asyncio.start_server(client, "127.0.0.1", 1119, ssl=context, ssl_handshake_timeout=10)
    event("modern_auth_started", port=1119)
    event("login_rest_started", port=18081)
    try:
        async with listener:
            await listener.serve_forever()
    finally:
        http.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
