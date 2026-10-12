import asyncio
import json
import websockets

async def test_streams():
    url = "wss://api.hyperliquid.xyz/ws"
    async with websockets.connect(url) as ws:
        subs = [
            {"method": "subscribe", "subscription": {"type": "l2Book", "coin": "BTC"}},
            {"method": "subscribe", "subscription": {"type": "trades", "coin": "BTC"}},
            {"method": "subscribe", "subscription": {"type": "activeAssetCtx", "coin": "BTC"}},
            {"method": "subscribe", "subscription": {"type": "candle", "coin": "BTC", "interval": "1m"}},
        ]
        for s in subs:
            await ws.send(json.dumps(s))

        received = {}
        for _ in range(25):
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(msg)
            ch = data.get("channel")
            if ch not in received:
                received[ch] = data.get("data")
                print(f"Captured channel: {ch}")
            if len(received) >= 4:
                break
        print("Channels successfully captured:", list(received.keys()))

if __name__ == "__main__":
    asyncio.run(test_streams())
