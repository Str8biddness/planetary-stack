import sys
import os
from queue import PriorityQueue

# Add root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cognitive.social_fabric import NPCMessage

def test_message_comparison():
    print("Testing NPCMessage comparison for PriorityQueue...")
    
    # Create two messages with the same priority (implicit in how PriorityQueue works with tuples)
    msg1 = NPCMessage(message_id="msg_b", sender_id="npc1", content="Hello")
    msg2 = NPCMessage(message_id="msg_a", sender_id="npc2", content="World")
    
    pq = PriorityQueue()
    
    # In a PriorityQueue, typically you might store (priority, message_obj)
    # The error occurred when priority was equal and it tried to compare the message objects.
    try:
        pq.put((1, msg1))
        pq.put((1, msg2))
        
        # This should not raise TypeError anymore
        first = pq.get()
        second = pq.get()
        
        print(f"Success! Retrieved: {first[1].message_id}, {second[1].message_id}")
        assert first[1].message_id == "msg_a" # msg_a < msg_b
        assert second[1].message_id == "msg_b"
        print("Comparison logic verified correctly (sorted by message_id).")
        return True
    except TypeError as e:
        print(f"FAILED: Comparison error still exists: {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return False

if __name__ == "__main__":
    if test_message_comparison():
        sys.exit(0)
    else:
        sys.exit(1)
