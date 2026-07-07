// Synthesus SDK — Unreal Engine Implementation
// AIVM LLC

#include "SynthesusClient.h"
#include "HttpModule.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "Serialization/JsonSerializer.h"
#include "Dom/JsonObject.h"


// ══════════════════════════════════════
// USynthesusClient
// ══════════════════════════════════════

void USynthesusClient::Chat(
    const FString& CharacterId,
    const FString& PlayerId,
    const FString& Message,
    FOnNPCResponse OnResponse)
{
    TSharedPtr<FJsonObject> RequestJson = MakeShared<FJsonObject>();
    RequestJson->SetStringField(TEXT("character_id"), CharacterId);
    RequestJson->SetStringField(TEXT("player_id"), PlayerId);
    RequestJson->SetStringField(TEXT("query"), Message);

    FString Body;
    TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Body);
    FJsonSerializer::Serialize(RequestJson.ToSharedRef(), Writer);

    float StartTime = FPlatformTime::Seconds();

    SendRequest(TEXT("/api/query"), TEXT("POST"), Body,
        [this, CharacterId, OnResponse, StartTime]
        (FHttpResponsePtr Response, bool bSuccess)
    {
        FSynthesusResponse Result;
        Result.CharacterId = CharacterId;
        Result.LatencyMs = (FPlatformTime::Seconds() - StartTime) * 1000.0f;

        if (bSuccess && Response.IsValid())
        {
            TSharedPtr<FJsonObject> JsonResponse;
            TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(
                Response->GetContentAsString());

            if (FJsonSerializer::Deserialize(Reader, JsonResponse) && JsonResponse.IsValid())
            {
                Result.Text = JsonResponse->GetStringField(TEXT("response"));
                Result.Confidence = JsonResponse->GetNumberField(TEXT("confidence"));
                Result.Emotion = JsonResponse->GetStringField(TEXT("emotion"));
                Result.Source = JsonResponse->GetStringField(TEXT("source"));
            }
        }
        else
        {
            Result.Text = TEXT("I'm having trouble thinking right now.");
            Result.Emotion = TEXT("confused");
            Result.Source = TEXT("error");
        }

        OnResponse.ExecuteIfBound(Result);
    });
}

void USynthesusClient::ListCharacters(FOnCharacterList OnComplete)
{
    SendRequest(TEXT("/api/characters"), TEXT("GET"), TEXT(""),
        [OnComplete](FHttpResponsePtr Response, bool bSuccess)
    {
        TArray<FSynthesusCharacter> Characters;

        if (bSuccess && Response.IsValid())
        {
            TSharedPtr<FJsonObject> JsonResponse;
            TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(
                Response->GetContentAsString());

            if (FJsonSerializer::Deserialize(Reader, JsonResponse) && JsonResponse.IsValid())
            {
                const TArray<TSharedPtr<FJsonValue>>* CharArray;
                if (JsonResponse->TryGetArrayField(TEXT("characters"), CharArray))
                {
                    for (const auto& CharValue : *CharArray)
                    {
                        TSharedPtr<FJsonObject> CharObj = CharValue->AsObject();
                        if (CharObj.IsValid())
                        {
                            FSynthesusCharacter Char;
                            Char.Id = CharObj->GetStringField(TEXT("id"));
                            Char.Name = CharObj->GetStringField(TEXT("name"));
                            Char.Role = CharObj->GetStringField(TEXT("role"));
                            Characters.Add(Char);
                        }
                    }
                }
            }
        }

        OnComplete.ExecuteIfBound(Characters);
    });
}

bool USynthesusClient::IsServerHealthy()
{
    // Synchronous health check (use with caution on game thread)
    FHttpModule& Http = FHttpModule::Get();
    TSharedRef<IHttpRequest> Request = Http.CreateRequest();
    Request->SetURL(ServerUrl + TEXT("/api/health"));
    Request->SetVerb(TEXT("GET"));
    Request->ProcessRequest();

    // Note: In production, use async version instead
    return true;
}

void USynthesusClient::SendRequest(
    const FString& Endpoint,
    const FString& Method,
    const FString& Body,
    TFunction<void(FHttpResponsePtr, bool)> Callback)
{
    TotalRequests++;

    FHttpModule& Http = FHttpModule::Get();
    TSharedRef<IHttpRequest> Request = Http.CreateRequest();
    Request->SetURL(ServerUrl + Endpoint);
    Request->SetVerb(Method);
    Request->SetHeader(TEXT("Content-Type"), TEXT("application/json"));

    if (!ApiKey.IsEmpty())
    {
        Request->SetHeader(TEXT("Authorization"), FString::Printf(TEXT("Bearer %s"), *ApiKey));
    }

    if (!Body.IsEmpty())
    {
        Request->SetContentAsString(Body);
    }

    Request->OnProcessRequestComplete().BindLambda(
        [Callback](FHttpRequestPtr Req, FHttpResponsePtr Resp, bool bConnected)
    {
        Callback(Resp, bConnected && Resp.IsValid() && Resp->GetResponseCode() == 200);
    });

    Request->ProcessRequest();
}


// ══════════════════════════════════════
// USynthesusNPCComponent
// ══════════════════════════════════════

USynthesusNPCComponent::USynthesusNPCComponent()
{
    PrimaryComponentTick.bCanEverTick = false;
}

void USynthesusNPCComponent::BeginPlay()
{
    Super::BeginPlay();
    Client = NewObject<USynthesusClient>(this);
    Client->ServerUrl = ServerUrl;
}

void USynthesusNPCComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    Client = nullptr;
    Super::EndPlay(EndPlayReason);
}

void USynthesusNPCComponent::Say(const FString& Message, FOnNPCResponse OnResponse)
{
    if (!Client) return;

    FOnNPCResponse WrappedCallback;
    WrappedCallback.BindLambda([this, OnResponse](const FSynthesusResponse& Response)
    {
        LastResponse = Response.Text;
        LastEmotion = Response.Emotion;
        LastConfidence = Response.Confidence;
        OnResponse.ExecuteIfBound(Response);
    });

    Client->Chat(CharacterId, PlayerId, Message, WrappedCallback);
}
