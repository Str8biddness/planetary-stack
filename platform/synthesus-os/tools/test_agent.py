import asyncio
from core.synthesus_master import SynthesusMaster

async def test_agent_dispatcher():
    print("Initializing SynthesusMaster...")
    master = SynthesusMaster()
    
    query = "Summarize the content on https://example.com"
    print(f"Sending query with URL: {query}")
    
    print("\n\n=== Testing Haven (Scraper Denied) ===")
    result_haven = await master.think(query=query, character_id="haven")
    print(f"Answer: {result_haven.get('answer')}")
    
    print("\n\n=== Testing Synth (Scraper Allowed) ===")
    result_synth = await master.think(query=query, character_id="synth")
    print(f"Answer: {result_synth.get('answer')}")

if __name__ == "__main__":
    asyncio.run(test_agent_dispatcher())
