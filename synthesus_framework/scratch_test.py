import asyncio
from api.production_server import _get_cognitive_engine, _load_character

async def main():
    char_data = _load_character("synthesus")
    print("Loaded character: ", char_data is not None)
    
    engine = _get_cognitive_engine("synthesus")
    print("CognitiveEngine: ", engine is not None)
    
    # Try pattern match
    res = engine._match_pattern("who are you")
    print("Matcher result:", res)
    
    # Try process query
    res2 = await engine.process_query(player_id="test", query="who are you", thinking_layer_available=True, ml_context={})
    print("Process query result:", res2)

if __name__ == "__main__":
    asyncio.run(main())
