import companion_ai.local_llm as local_llm
from companion_ai.core import config as core_config


def test_local_llm_prefers_ollama_in_hybrid(monkeypatch):
    monkeypatch.setattr(core_config, 'get_effective_local_model_runtime', lambda: 'hybrid')
    monkeypatch.setattr(local_llm.OllamaBackend, 'is_available', lambda self: True)
    monkeypatch.setattr(local_llm.VLLMBackend, 'is_available', lambda self: True)

    llm = local_llm.LocalLLM()

    assert isinstance(llm.backend, local_llm.OllamaBackend)
    assert isinstance(llm.get_client(), local_llm.OllamaClientWrapper)


def test_local_llm_uses_vllm_when_runtime_forced(monkeypatch):
    monkeypatch.setattr(core_config, 'get_effective_local_model_runtime', lambda: 'vllm')
    monkeypatch.setattr(local_llm.OllamaBackend, 'is_available', lambda self: True)
    monkeypatch.setattr(local_llm.VLLMBackend, 'is_available', lambda self: True)
    monkeypatch.setattr(local_llm.VLLMBackend, 'get_current_model', lambda self: 'Qwen/Qwen2.5-3B-Instruct')

    llm = local_llm.LocalLLM()

    assert isinstance(llm.backend, local_llm.VLLMBackend)
    assert isinstance(llm.get_client(), local_llm.VLLMClientWrapper)


def test_local_llm_unavailable_when_forced_runtime_missing(monkeypatch):
    monkeypatch.setattr(core_config, 'get_effective_local_model_runtime', lambda: 'ollama')
    monkeypatch.setattr(local_llm.OllamaBackend, 'is_available', lambda self: False)

    llm = local_llm.LocalLLM()

    assert llm.backend is None
    assert llm.is_available() is False
