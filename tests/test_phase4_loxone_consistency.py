import asyncio

from companion_ai.local_loops.base import LoopStatus
from companion_ai.local_loops.tool_loop import ToolLoop


def test_tool_loop_light_dim_uses_set_brightness(monkeypatch):
    async def fake_set_brightness(room, brightness):
        return {
            'success': True,
            'room': room,
            'brightness': brightness,
            'mode': 'dim',
            'message': 'ok',
        }

    import companion_ai.integrations.loxone as loxone_module
    monkeypatch.setattr(loxone_module, 'set_brightness', fake_set_brightness)

    loop = ToolLoop()
    result = asyncio.run(loop._light_dim('kitchen', 25))

    assert result.status == LoopStatus.SUCCESS
    assert result.data['room'] == 'kitchen'
    assert result.data['brightness'] == 25


def test_tool_loop_light_dim_propagates_failure(monkeypatch):
    async def fake_set_brightness(room, brightness):
        return {
            'success': False,
            'error': 'Unknown room',
        }

    import companion_ai.integrations.loxone as loxone_module
    monkeypatch.setattr(loxone_module, 'set_brightness', fake_set_brightness)

    loop = ToolLoop()
    result = asyncio.run(loop._light_dim('not-a-room', 50))

    assert result.status == LoopStatus.ERROR
    assert 'Unknown room' in (result.error or '')
