// Synthesus SDK — Unreal Engine C++ Client
// AIVM LLC — Drop into your Unreal project's Source/ folder
//
// Usage:
//   USynthesusClient* Client = NewObject<USynthesusClient>();
//   Client->ServerUrl = TEXT("http://localhost:8000");
//   Client->Chat(TEXT("merchant_01"), TEXT("player_1"), TEXT("Hello!"),
//     [](const FSynthesusResponse& Response) {
//       UE_LOG(LogTemp, Log, TEXT("NPC: %s"), *Response.Text);
//     });
//
// Requires: HTTP module (built-in), Json module (built-in)
// Tested: UE 5.1+, 5.3+, 5.4+

#pragma once

#include "CoreMinimal.h"
#include "UObject/NoExportTypes.h"
#include "Http.h"
#include "Json.h"
#include "SynthesusClient.generated.h"


// ── Response Types ──

USTRUCT(BlueprintType)
struct FSynthesusResponse
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly)
    FString Text;

    UPROPERTY(BlueprintReadOnly)
    float Confidence = 0.0f;

    UPROPERTY(BlueprintReadOnly)
    FString Emotion;

    UPROPERTY(BlueprintReadOnly)
    FString Source;

    UPROPERTY(BlueprintReadOnly)
    FString CharacterId;

    UPROPERTY(BlueprintReadOnly)
    float LatencyMs = 0.0f;
};


USTRUCT(BlueprintType)
struct FSynthesusCharacter
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly)
    FString Id;

    UPROPERTY(BlueprintReadOnly)
    FString Name;

    UPROPERTY(BlueprintReadOnly)
    FString Role;
};


// ── Delegates ──

DECLARE_DYNAMIC_DELEGATE_OneParam(FOnNPCResponse, const FSynthesusResponse&, Response);
DECLARE_DYNAMIC_DELEGATE_OneParam(FOnCharacterList, const TArray<FSynthesusCharacter>&, Characters);


// ── SDK Client ──

UCLASS(BlueprintType, Blueprintable)
class USynthesusClient : public UObject
{
    GENERATED_BODY()

public:
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Synthesus")
    FString ServerUrl = TEXT("http://localhost:8000");

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Synthesus")
    FString ApiKey;

    /**
     * Send a message to an NPC and get their response via callback.
     */
    UFUNCTION(BlueprintCallable, Category = "Synthesus")
    void Chat(
        const FString& CharacterId,
        const FString& PlayerId,
        const FString& Message,
        FOnNPCResponse OnResponse);

    /**
     * List all available characters.
     */
    UFUNCTION(BlueprintCallable, Category = "Synthesus")
    void ListCharacters(FOnCharacterList OnComplete);

    /**
     * Check server health (returns true if reachable).
     */
    UFUNCTION(BlueprintCallable, Category = "Synthesus")
    bool IsServerHealthy();

    UPROPERTY(BlueprintReadOnly, Category = "Synthesus")
    int32 TotalRequests = 0;

private:
    void SendRequest(
        const FString& Endpoint,
        const FString& Method,
        const FString& Body,
        TFunction<void(FHttpResponsePtr, bool)> Callback);
};


// ── Actor Component ──

UCLASS(ClassGroup = (Synthesus), meta = (BlueprintSpawnableComponent))
class USynthesusNPCComponent : public UActorComponent
{
    GENERATED_BODY()

public:
    USynthesusNPCComponent();

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Synthesus|Config")
    FString ServerUrl = TEXT("http://localhost:8000");

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Synthesus|Config")
    FString CharacterId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Synthesus|Config")
    FString PlayerId = TEXT("player_1");

    UPROPERTY(BlueprintReadOnly, Category = "Synthesus|State")
    FString LastResponse;

    UPROPERTY(BlueprintReadOnly, Category = "Synthesus|State")
    FString LastEmotion;

    UPROPERTY(BlueprintReadOnly, Category = "Synthesus|State")
    float LastConfidence = 0.0f;

    /**
     * Send a message to this NPC. Call from dialogue UI, proximity triggers, etc.
     */
    UFUNCTION(BlueprintCallable, Category = "Synthesus")
    void Say(const FString& Message, FOnNPCResponse OnResponse);

protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
    UPROPERTY()
    USynthesusClient* Client;
};
