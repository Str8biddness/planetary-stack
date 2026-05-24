import asyncio
from cognitive.pattern_engine import PatternEngine

async def main():
    engine = PatternEngine()
    
    # Mock KAL context to bypass RAG dependency
    kal_mock = {
        "results": [
            type("Node", (object,), {"content": "A: The artificial intelligence system woke up."})()
        ]
    }
    
    print("Testing generate_response...")
    try:
        res = await engine.generate_response("tell me a story", kal_mock)
        print("Result:", res)
    except Exception as e:
        print("Exception caught:", e)

if __name__ == "__main__":
    asyncio.run(main())
