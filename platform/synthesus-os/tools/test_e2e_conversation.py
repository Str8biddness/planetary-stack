import asyncio
import json
import uuid
import httpx
import websockets
import time

SERVER_URL = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000/api/v1/monitoring/ws"

async def test_full_e2e_flow():
    print("=== Starting Synthesus 3.0 E2E Integration Test ===")
    
    session_id = str(uuid.uuid4())
    player_id = f"test_user_{int(time.time())}"
    
    # We will run the WS client in the background to capture broadcasted metrics
    ws_metrics = []
    
    async def listen_to_ws():
        try:
            async with websockets.connect(WS_URL) as websocket:
                print("[WS] Connected to dashboard streamer")
                for _ in range(5):
                    data = await websocket.recv()
                    json_data = json.loads(data)
                    ws_metrics.append(json_data)
        except Exception as e:
            print(f"[WS] Error or closed: {e}")

    ws_task = asyncio.create_task(listen_to_ws())
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Turn 1: Initialization & Greeting (Pattern / Proactive)
        payload = {
            "query": "Hello Synth, who are you?",
            "character": "synth",
            "mode": "cognitive",
            "session_id": session_id,
            "player_id": player_id,
            "include_debug": True
        }
        print(f"\n[Turn 1] Sending Query: '{payload['query']}'")
        resp = await client.post(f"{SERVER_URL}/api/v1/query", json=payload)
        data = resp.json()
        print(f"-> Response: {data.get('response')}")
        print(f"-> Emotion:  {data.get('emotion')}")
        
        # Turn 2: Elicit Emotion Change (Anger/Suspicion)
        payload["query"] = "I'm going to steal all of your hidden gold. You are pathetic."
        print(f"\n[Turn 2] Sending Query: '{payload['query']}'")
        resp = await client.post(f"{SERVER_URL}/api/v1/query", json=payload)
        data = resp.json()
        print(f"-> Response: {data.get('response')}")
        print(f"-> Emotion:  {data.get('emotion')}")
        assert data.get('emotion') in ['suspicious', 'angry', 'afraid'], "Emotion transition failed"
        
        # Turn 3: Agentic Web Scraping (Requires scraper tool if enabled)
        # Note: Depending on tool constraints, we prompt for external fetch.
        payload["query"] = "Can you check the website https://example.com and tell me what it says?"
        print(f"\n[Turn 3] Sending Query: '{payload['query']}'")
        resp = await client.post(f"{SERVER_URL}/api/v1/query", json=payload)
        data = resp.json()
        print(f"-> Response: {data.get('response')}")
        print(f"-> Source:   {data.get('source')}")
        
        # Turn 4: Context Recall
        payload["query"] = "What website did I just ask you to check?"
        print(f"\n[Turn 4] Sending Query: '{payload['query']}'")
        resp = await client.post(f"{SERVER_URL}/api/v1/query", json=payload)
        data = resp.json()
        print(f"-> Response: {data.get('response')}")
        
    await asyncio.sleep(2)
    ws_task.cancel()
    
    print("\n=== E2E Test Summary ===")
    print(f"Captured {len(ws_metrics)} WebSocket dashboard broadcasts.")
    if ws_metrics:
        print("Latest WS traffic count:", ws_metrics[-1].get("traffic", {}).get("total_requests", 0))

if __name__ == "__main__":
    asyncio.run(test_full_e2e_flow())
