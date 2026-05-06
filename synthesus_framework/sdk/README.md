# Synthesus SDK — Game Engine Integration

> Drop-in NPC intelligence for any game engine or application.

## Available SDKs

| Platform | Language | File | Status |
|----------|----------|------|--------|
| Python (Pygame, Godot, etc.) | Python 3.10+ | `python/synthesus_sdk.py` | Production |
| Unity | C# | `unity/SynthesusClient.cs` | Production |
| Unreal Engine | C++ | `unreal/SynthesusClient.h/.cpp` | Production |

## Quick Start

### Python
```python
from synthesus_sdk import SynthesusClient

client = SynthesusClient("http://localhost:8000")
response = client.chat("merchant_01", "player_1", "What do you sell?")
print(response.text)        # "Welcome! I have potions, swords, and armor."
print(response.confidence)  # 0.85
print(response.emotion)     # "friendly"
```

### Unity (C#)
```csharp
// Attach SynthesusNPC component to any GameObject
var npc = gameObject.AddComponent<SynthesusNPC>();
npc.serverUrl = "http://localhost:8000";
npc.characterId = "merchant_01";
npc.Say("Hello!", response => {
    dialogueUI.ShowText(response.text);
    animator.SetTrigger(response.emotion);
});
```

### Unreal Engine (C++)
```cpp
// Add USynthesusNPCComponent to any Actor via Blueprint or C++
USynthesusNPCComponent* NPC = CreateDefaultSubobject<USynthesusNPCComponent>(TEXT("NPC"));
NPC->ServerUrl = TEXT("http://localhost:8000");
NPC->CharacterId = TEXT("merchant_01");

// In response to player interaction:
NPC->Say(TEXT("Hello!"), FOnNPCResponse::CreateLambda([](const FSynthesusResponse& R) {
    UE_LOG(LogTemp, Log, TEXT("NPC says: %s [%s]"), *R.Text, *R.Emotion);
}));
```

## Server Setup

The SDK connects to a Synthesus API server. Start it with:

```bash
cd synthesus/
python api/fastapi_server.py
# Server runs on http://localhost:8000
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/query` | POST | Chat with an NPC |
| `/api/characters` | GET | List all characters |
| `/api/characters/{id}` | GET | Get character details |
| `/api/world/state` | GET | Get world state |
| `/api/world/tick` | POST | Advance world tick |
| `/api/save` | POST | Save game state |
| `/api/load` | POST | Load game state |
| `/api/health` | GET | Server health check |

## Architecture

```
Game Engine (Unity/Unreal/Python)
        |
    [SDK Client]  ← HTTP/JSON
        |
    [FastAPI Server]  ← Port 8000
        |
    [CognitiveEngine]
        |
    ┌───┴───┐
    │ Right  │  Left Hemisphere
    │ Hemi   │  (Pattern + Semantic)
    │ (Fast) │
    └───┬───┘
        |
    [Response]
```
