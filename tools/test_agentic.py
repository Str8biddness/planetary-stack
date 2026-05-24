
import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from core.synthesus_master import SynthesusMaster

async def test_agentic_master():
    print("--- Starting End-to-End Agentic Test ---")
    master = SynthesusMaster()
    
    # Test: Scrape a real URL
    query = "Scrape https://example.com and tell me what is on the page."
    print(f"\nUser Query: {query}")
    
    result = await master.think(query)
    
    # Handle potentially complex unicode characters in generated text for Windows terminal
    print("\nMaster Answer:")
    print(result['answer'].encode('ascii', 'replace').decode('ascii'))
    
    event = result['event']
    print(f"\nEngines Used: {event.engines_used}")
    print(f"Actions Taken: {event.actions_taken}")
    
    # Check if the answer contains something from example.com or mentions the scraper
    if "Example Domain" in result['answer'] or "scraper" in result['answer'].lower():
        print("\nSUCCESS: Tool result correctly rendered in Master answer!")
    elif len(event.actions_taken) > 0:
        print("\nPARTIAL SUCCESS: Tool was used, but answer rendering might be subtle.")
    else:
        print("\nFAILURE: Tool was not used or result not propagated.")

if __name__ == "__main__":
    asyncio.run(test_agentic_master())
