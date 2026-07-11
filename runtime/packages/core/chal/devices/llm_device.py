import os
import time
import requests
from typing import Tuple, Dict, Any, Union

from packages.core.chal.frames import CognitiveTask, TelemetryRecord
from packages.core.sllm_coordinator import SllmCoordinator

class LLMGenerationDevice(SllmCoordinator):
    """
    Wraps Ollama as a CHAL cognitive device.
    Fulfills C-201 Callout:
    - Input: CognitiveTask -> output text + telemetry
    - Real Ollama call
    - On timeout/error: returns a structured error frame (never a fabricated string).
    - Honors budget_ms. Emits TelemetryRecord every call.
    """
    # Who the model is. Establishes identity so it knows it is Synthesus (not a
    # generic Llama, and not the old 'Ghostkey' default). Overridable via env.
    DEFAULT_SYSTEM_PROMPT = (
        "You are Synthesus, a private AI that runs entirely on the user's own machine — "
        "nothing they do leaves their computer. You can ground your answers in the user's "
        "own files and documents through their expansion drive. Be clear, direct, and "
        "genuinely helpful. When knowledge context is provided, ground your answer in it "
        "and do not invent facts; if you don't know, say so plainly. Your name is "
        "Synthesus — never claim to be any other assistant, model, or persona."
    )

    def __init__(self, engine=None):
        super().__init__(engine)
        self.model_name = os.getenv("SYNTHESUS_MODEL", "llama3.2:3b")
        self.api_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")
        self.system_prompt = os.getenv("SYNTHESUS_SYSTEM_PROMPT", self.DEFAULT_SYSTEM_PROMPT)

    def generate(self, task: CognitiveTask, system_prompt: str = None) -> Tuple[Union[str, Dict[str, Any]], TelemetryRecord]:
        start_time = time.time()
        budget_ms = task.budgets.get("latency_ms", 60000.0)
        timeout_s = budget_ms / 1000.0

        try:
            import json
            settings_path = os.path.join(
                os.environ.get("SYNTHESUS_HOME", os.path.expanduser("~/.local/share/synthesus")),
                "settings.json"
            )
            settings = {}
            if os.path.exists(settings_path):
                with open(settings_path, "r") as f:
                    settings = json.load(f)
            
            provider = os.getenv("SYNTHESUS_LLM_PROVIDER") or settings.get("llm_provider", "ollama")
            model_name = settings.get("model") or self.model_name
            api_key = settings.get("api_key", "").strip()
            
            sys_prompt = system_prompt or self.system_prompt
            prompt = task.query

            if provider not in ("ollama", "lmstudio") and not api_key:
                raise ValueError(f"API key missing for provider: {provider}")

            if provider == "openai":
                url = "https://api.openai.com/v1/chat/completions"
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": prompt}
                    ]
                }
                response = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
                response.raise_for_status()
                output = response.json()["choices"][0]["message"]["content"]
            elif provider == "anthropic":
                url = "https://api.anthropic.com/v1/messages"
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                payload = {
                    "model": model_name,
                    "max_tokens": 4096,
                    "system": sys_prompt,
                    "messages": [{"role": "user", "content": prompt}]
                }
                response = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
                response.raise_for_status()
                output = response.json()["content"][0]["text"]
            elif provider == "gemini":
                # Key goes in a header, NOT the URL query string — a key in the URL
                # leaks into request/exception messages ("...for url: ...?key=...").
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
                headers = {"x-goog-api-key": api_key, "content-type": "application/json"}
                payload = {
                    "systemInstruction": {"parts": [{"text": sys_prompt}]},
                    "contents": [{"parts": [{"text": prompt}]}]
                }
                response = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
                response.raise_for_status()
                output = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            elif provider == "lmstudio":
                base_url = settings.get("lmstudio_base_url", "http://localhost:1234").rstrip("/")
                url = f"{base_url}/v1/chat/completions"
                headers = {"Content-Type": "application/json"}
                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": prompt}
                    ]
                }
                response = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
                response.raise_for_status()
                output = response.json()["choices"][0]["message"]["content"]
            elif provider == "ollama_cloud":
                raise NotImplementedError("BLOCKED: Law #1 - Ollama does not have a documented real cloud API endpoint.")
            else: # ollama
                payload = {
                    "model": model_name,
                    "system": sys_prompt,
                    "prompt": prompt,
                    "stream": False
                }
                response = requests.post(self.api_url, json=payload, timeout=timeout_s)
                response.raise_for_status()
                output = response.json().get("response", "")
            
            latency_ms = (time.time() - start_time) * 1000.0
            telemetry = TelemetryRecord(
                trace_id=task.trace_id,
                component="llm_device",
                latency_ms=latency_ms,
                confidence=0.9,
                metadata={"model": model_name, "provider": provider, "status": "success"}
            )
            return output, telemetry
            
        except requests.exceptions.Timeout:
            latency_ms = (time.time() - start_time) * 1000.0
            error_frame = {
                "error": "TimeoutError",
                "message": f"{provider} generation exceeded budget of {budget_ms}ms"
            }
            telemetry = TelemetryRecord(
                trace_id=task.trace_id,
                component="llm_device",
                latency_ms=latency_ms,
                confidence=0.0,
                fallback_used=True,
                metadata={"model": model_name if 'model_name' in locals() else self.model_name, "status": "timeout"}
            )
            return error_frame, telemetry
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000.0
            # Belt-and-suspenders: never let a provider key leak into an error
            # message that might be logged or surfaced.
            _msg = str(e)
            if 'api_key' in locals() and api_key:
                _msg = _msg.replace(api_key, "***REDACTED***")
            error_frame = {
                "error": type(e).__name__,
                "message": _msg
            }
            telemetry = TelemetryRecord(
                trace_id=task.trace_id,
                component="llm_device",
                latency_ms=latency_ms,
                confidence=0.0,
                fallback_used=True,
                metadata={"model": model_name if 'model_name' in locals() else self.model_name, "status": "error"}
            )
            return error_frame, telemetry

if __name__ == "__main__":
    import unittest
    from unittest.mock import patch, MagicMock

    class TestLLMDevice(unittest.TestCase):
        def setUp(self):
            self.task = CognitiveTask(task_id="task123", query="hello", trace_id="trace123", budgets={"latency_ms": 1000})
            self.device = LLMGenerationDevice()

        @patch("requests.post")
        @patch("os.path.exists", return_value=True)
        @patch("builtins.open", new_callable=unittest.mock.mock_open, read_data='{"llm_provider": "ollama", "model": "test-model"}')
        def test_ollama_default_unchanged(self, mock_open, mock_exists, mock_post):
            mock_response = MagicMock()
            mock_response.json.return_value = {"response": "Hi there"}
            mock_post.return_value = mock_response

            output, tel = self.device.generate(self.task)
            self.assertEqual(output, "Hi there")
            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            self.assertEqual(args[0], "http://localhost:11434/api/generate")
            self.assertEqual(kwargs["json"]["model"], "test-model")
            self.assertEqual(kwargs["json"]["prompt"], "hello")

        @patch("requests.post")
        @patch("os.path.exists", return_value=True)
        @patch("builtins.open", new_callable=unittest.mock.mock_open, read_data='{"llm_provider": "lmstudio", "lmstudio_base_url": "http://my-studio", "model": "local-model"}')
        def test_lmstudio(self, mock_open, mock_exists, mock_post):
            mock_response = MagicMock()
            mock_response.json.return_value = {"choices": [{"message": {"content": "LM Studio output"}}]}
            mock_post.return_value = mock_response

            output, tel = self.device.generate(self.task)
            self.assertEqual(output, "LM Studio output")
            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            self.assertEqual(args[0], "http://my-studio/v1/chat/completions")
            self.assertEqual(kwargs["headers"], {"Content-Type": "application/json"})
            self.assertEqual(kwargs["json"]["model"], "local-model")
            self.assertEqual(kwargs["json"]["messages"][1]["content"], "hello")

        @patch("requests.post")
        @patch("os.path.exists", return_value=True)
        @patch("builtins.open", new_callable=unittest.mock.mock_open, read_data='{"llm_provider": "ollama_cloud", "api_key": "somekey"}')
        def test_ollama_cloud_blocked(self, mock_open, mock_exists, mock_post):
            output, tel = self.device.generate(self.task)
            self.assertIsInstance(output, dict)
            self.assertEqual(output["error"], "NotImplementedError")
            self.assertIn("BLOCKED", output["message"])

        @patch("requests.post")
        @patch("os.path.exists", return_value=True)
        @patch("builtins.open", new_callable=unittest.mock.mock_open, read_data='{"llm_provider": "openai", "api_key": "supersecretkey"}')
        def test_token_redaction_on_error(self, mock_open, mock_exists, mock_post):
            mock_post.side_effect = Exception("Failed to connect with key supersecretkey")
            output, tel = self.device.generate(self.task)
            self.assertIsInstance(output, dict)
            self.assertNotIn("supersecretkey", output["message"])
            self.assertIn("***REDACTED***", output["message"])

        @patch("requests.post")
        @patch("os.path.exists", return_value=True)
        @patch("builtins.open", new_callable=unittest.mock.mock_open, read_data='{"llm_provider": "lmstudio"}')
        def test_http_error_dict(self, mock_open, mock_exists, mock_post):
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
            mock_post.return_value = mock_response

            output, tel = self.device.generate(self.task)
            self.assertIsInstance(output, dict)
            self.assertEqual(output["error"], "HTTPError")
            self.assertEqual(output["message"], "404 Not Found")

    unittest.main(verbosity=2)
