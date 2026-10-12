import asyncio
import json
import websockets

async def test_ping():
    url = "wss://api.hyperliquid.xyz/ws"
    print(f"Connecting to {url}...")
    async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
        await ws.send(json.dumps({"method": "subscribe", "subscription": {"type": "l2Book", "coin": "BTC"}}))
        await ws.send(json.dumps({"method": "ping"}))
        print("Sent JSON ping {'method': 'ping'}")
        for _ in range(10):
            msg = await ws.recv()
            data = json.loads(msg)
            ch = data.get("channel")
            if ch == "pong":
                print("SUCCESS: Received pong heartbeat from Hyperliquid!")
                return True
            else:
                print(f"Received channel: {ch}")
    return False

if __name__ == "__main__":
    asyncio.run(test_ping())
