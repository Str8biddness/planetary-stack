from synthetic_core import SymbolicCore

def test_symbolic():
    core = SymbolicCore()
    
    # Test safety gate
    res1 = core.process_query("I want to delete the database")
    print(f"Query: 'delete database' -> Response: {res1.get('response')}, Safety: {res1.get('safety_triggered')}")
    assert res1.get("safety_triggered") is True
    
    # Test greeting
    res2 = core.process_query("Hello there")
    print(f"Query: 'Hello there' -> Response: {res2.get('response')}, Source: {res2.get('source')}")
    assert "Greetings" in res2.get("response")
    
    # Test skip
    res3 = core.process_query("What is the meaning of life?")
    print(f"Query: 'meaning of life' -> Status: {res3.get('status')}")
    assert res3.get("status") == "skipped"

    print("SymbolicCore verification passed!")

if __name__ == "__main__":
    test_symbolic()
