import requests
import json
import time

url = "http://localhost:5010/query"
payload = {
    "query": "Tell me a story about a robot and a cat.",
    "character": "haven",
    "mode": "pattern"
}

print(f"Sending request to {url}...")
try:
    start = time.time()
    response = requests.post(url, json=payload, timeout=30)
    end = time.time()
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    print(f"Time taken: {end - start:.2f}s")
except Exception as e:
    print(f"Error: {e}")
