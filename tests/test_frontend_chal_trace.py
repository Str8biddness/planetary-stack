from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_chat_frontend_exposes_chal_modes_and_trace_panel():
    app = (PROJECT_ROOT / "packages/frontend/src/App.tsx").read_text()
    chat_window = (PROJECT_ROOT / "packages/frontend/src/components/ChatWindow.tsx").read_text()
    styles = (PROJECT_ROOT / "packages/frontend/src/App.css").read_text()
    types = (PROJECT_ROOT / "packages/frontend/src/types.ts").read_text()

    assert '<option value="chal">Synthesus 5 CHAL</option>' in app
    assert '<option value="business_bot">Business Bot</option>' in app

    assert "interface CHALTelemetry" in types
    assert "cognitive_hypervisor" in chat_window
    assert "CHAL Trace" in chat_window
    assert "Quad Brain" in chat_window
    assert "Degraded State" in chat_window
    assert "Memory Writeback" in chat_window
    assert "Template Guard" in chat_window

    assert ".chal-trace-panel" in styles
    assert ".chal-route-pill.degraded" in styles
