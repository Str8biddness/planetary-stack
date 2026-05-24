/*
 * Synthesus SDK — Unity C# Client
 * AIVM LLC — Drop into any Unity project's Assets/ folder
 *
 * Usage:
 *   var client = new SynthesusClient("http://localhost:8000");
 *   var response = await client.ChatAsync("merchant_01", "player_1", "Hello!");
 *   Debug.Log(response.Text);
 *
 * Dependencies: UnityEngine, System.Net.Http (built-in)
 * Tested: Unity 2021.3+, 2022.3+, 6.x
 */

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using UnityEngine;

namespace AIVM.Synthesus
{
    // ── Response Types ──

    [Serializable]
    public class NPCResponse
    {
        public string text;
        public float confidence;
        public string emotion;
        public string source;
        public string characterId;
        public float latencyMs;
    }

    [Serializable]
    public class CharacterInfo
    {
        public string id;
        public string name;
        public string role;
    }

    [Serializable]
    public class HealthStatus
    {
        public string status;
        public int activeCharacters;
        public int totalQueries;
    }

    // ── Internal JSON Models ──

    [Serializable]
    internal class QueryRequest
    {
        public string character_id;
        public string player_id;
        public string query;
    }

    [Serializable]
    internal class QueryResponse
    {
        public string response;
        public float confidence;
        public string emotion;
        public string source;
    }

    [Serializable]
    internal class CharacterListResponse
    {
        public List<CharacterInfo> characters;
    }

    // ── SDK Client ──

    public class SynthesusClient : IDisposable
    {
        private readonly string _baseUrl;
        private readonly HttpClient _http;
        private int _totalRequests;
        private float _totalLatencyMs;

        /// <summary>
        /// Create a new Synthesus client.
        /// </summary>
        /// <param name="baseUrl">Server URL (e.g., "http://localhost:8000")</param>
        /// <param name="apiKey">Optional API key</param>
        /// <param name="timeoutSeconds">Request timeout</param>
        public SynthesusClient(
            string baseUrl = "http://localhost:8000",
            string apiKey = null,
            float timeoutSeconds = 30f)
        {
            _baseUrl = baseUrl.TrimEnd('/');
            _http = new HttpClient
            {
                Timeout = TimeSpan.FromSeconds(timeoutSeconds)
            };
            _http.DefaultRequestHeaders.Add("Accept", "application/json");
            if (!string.IsNullOrEmpty(apiKey))
            {
                _http.DefaultRequestHeaders.Add("Authorization", $"Bearer {apiKey}");
            }
        }

        // ── NPC Chat ──

        /// <summary>
        /// Send a message to an NPC and get their response.
        /// </summary>
        public async Task<NPCResponse> ChatAsync(
            string characterId, string playerId, string message)
        {
            var startTime = Time.realtimeSinceStartup;

            var request = new QueryRequest
            {
                character_id = characterId,
                player_id = playerId,
                query = message
            };

            var json = JsonUtility.ToJson(request);
            var content = new StringContent(json, Encoding.UTF8, "application/json");

            _totalRequests++;
            var httpResponse = await _http.PostAsync($"{_baseUrl}/api/query", content);
            httpResponse.EnsureSuccessStatusCode();

            var responseJson = await httpResponse.Content.ReadAsStringAsync();
            var data = JsonUtility.FromJson<QueryResponse>(responseJson);

            var latency = (Time.realtimeSinceStartup - startTime) * 1000f;
            _totalLatencyMs += latency;

            return new NPCResponse
            {
                text = data.response,
                confidence = data.confidence,
                emotion = data.emotion,
                source = data.source,
                characterId = characterId,
                latencyMs = latency
            };
        }

        /// <summary>
        /// Coroutine-friendly wrapper for use in MonoBehaviours.
        /// Usage: StartCoroutine(client.Chat("npc", "player", "hi", r => Debug.Log(r.text)));
        /// </summary>
        public System.Collections.IEnumerator Chat(
            string characterId, string playerId, string message,
            Action<NPCResponse> callback)
        {
            var task = ChatAsync(characterId, playerId, message);
            while (!task.IsCompleted) yield return null;

            if (task.IsFaulted)
            {
                Debug.LogError($"Synthesus chat error: {task.Exception?.Message}");
                callback?.Invoke(new NPCResponse
                {
                    text = "I'm having trouble thinking right now.",
                    confidence = 0f,
                    emotion = "confused",
                    source = "error"
                });
            }
            else
            {
                callback?.Invoke(task.Result);
            }
        }

        // ── Character Management ──

        /// <summary>
        /// List all available NPC characters.
        /// </summary>
        public async Task<List<CharacterInfo>> ListCharactersAsync()
        {
            _totalRequests++;
            var response = await _http.GetAsync($"{_baseUrl}/api/characters");
            response.EnsureSuccessStatusCode();
            var json = await response.Content.ReadAsStringAsync();
            var data = JsonUtility.FromJson<CharacterListResponse>(json);
            return data.characters ?? new List<CharacterInfo>();
        }

        // ── Health ──

        /// <summary>
        /// Check server health.
        /// </summary>
        public async Task<HealthStatus> HealthAsync()
        {
            _totalRequests++;
            var response = await _http.GetAsync($"{_baseUrl}/api/health");
            response.EnsureSuccessStatusCode();
            var json = await response.Content.ReadAsStringAsync();
            return JsonUtility.FromJson<HealthStatus>(json);
        }

        // ── Stats ──

        public int TotalRequests => _totalRequests;
        public float AverageLatencyMs =>
            _totalRequests > 0 ? _totalLatencyMs / _totalRequests : 0f;

        public void Dispose()
        {
            _http?.Dispose();
        }
    }

    // ── MonoBehaviour Component ──

    /// <summary>
    /// Drop this onto any GameObject to add Synthesus NPC intelligence.
    /// Configure in the Inspector.
    /// </summary>
    public class SynthesusNPC : MonoBehaviour
    {
        [Header("Server")]
        public string serverUrl = "http://localhost:8000";
        public string apiKey = "";

        [Header("Character")]
        public string characterId = "merchant_01";
        public string playerId = "player_1";

        [Header("State")]
        [SerializeField] private string lastResponse;
        [SerializeField] private string lastEmotion;
        [SerializeField] private float lastConfidence;

        private SynthesusClient _client;

        void Start()
        {
            _client = new SynthesusClient(serverUrl, apiKey);
        }

        /// <summary>
        /// Send a message to this NPC. Call from dialogue UI, proximity trigger, etc.
        /// </summary>
        public void Say(string message, Action<NPCResponse> onResponse = null)
        {
            StartCoroutine(_client.Chat(characterId, playerId, message, response =>
            {
                lastResponse = response.text;
                lastEmotion = response.emotion;
                lastConfidence = response.confidence;
                onResponse?.Invoke(response);
            }));
        }

        void OnDestroy()
        {
            _client?.Dispose();
        }
    }
}
