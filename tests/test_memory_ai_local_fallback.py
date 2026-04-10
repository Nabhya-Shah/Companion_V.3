from types import SimpleNamespace

import companion_ai.memory.ai_processor as ai_processor


class _FakeGroqClient:
    class _Chat:
        class _Completions:
            @staticmethod
            def create(**kwargs):
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content='fallback-ok')
                        )
                    ]
                )

        completions = _Completions()

    chat = _Chat()


class _BrokenLocalLLM:
    def is_available(self):
        return True

    def generate(self, prompt: str, model: str = None):
        raise RuntimeError('local failure')


def test_generate_memory_response_falls_back_when_local_generation_fails(monkeypatch):
    monkeypatch.setattr(ai_processor.core_config, 'get_memory_processing_model', lambda **kwargs: ('qwen2.5:7b', True, 'local'))
    monkeypatch.setattr(ai_processor, 'groq_memory_client', _FakeGroqClient())

    import companion_ai.local_llm as local_llm

    monkeypatch.setattr(local_llm, 'LocalLLM', _BrokenLocalLLM)

    out = ai_processor.generate_memory_response('hello memory', purpose='facts', importance=0.6)

    assert out == 'fallback-ok'
