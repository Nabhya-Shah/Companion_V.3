import io

import web_companion
from web_companion import app
import companion_ai.web.files_routes as _files_mod


def test_upload_batch_mixed_results(tmp_path, monkeypatch):
    monkeypatch.setattr(_files_mod, 'UPLOAD_DIR', str(tmp_path))

    client = app.test_client()
    res = client.post(
        '/api/upload/batch',
        data={
            'files': [
                (io.BytesIO(b'hello'), 'note.txt'),
                (io.BytesIO(b'%PDF-1.4 test'), 'doc.pdf'),
                (io.BytesIO(b'bad'), 'malware.exe'),
            ]
        },
        content_type='multipart/form-data',
    )

    assert res.status_code == 200
    payload = res.get_json()
    assert payload['success'] is True
    assert payload['count'] == 2
    assert len(payload['uploaded']) == 2
    assert any(err['filename'] == 'malware.exe' for err in payload['errors'])


def test_upload_list_returns_recent_files(tmp_path, monkeypatch):
    monkeypatch.setattr(_files_mod, 'UPLOAD_DIR', str(tmp_path))
    (tmp_path / 'abc12345.txt').write_text('a', encoding='utf-8')
    (tmp_path / 'def67890.pdf').write_text('b', encoding='utf-8')

    client = app.test_client()
    res = client.get('/api/upload/list?limit=10')

    assert res.status_code == 200
    payload = res.get_json()
    assert payload['count'] == 2
    assert len(payload['files']) == 2
    assert payload['files'][0]['url'].startswith('/api/upload/')


def test_upload_extract_text(tmp_path, monkeypatch):
    monkeypatch.setattr(_files_mod, 'UPLOAD_DIR', str(tmp_path))
    (tmp_path / 'alpha1234.txt').write_text('hello extraction world', encoding='utf-8')

    client = app.test_client()
    res = client.post('/api/upload/extract', json={'file_id': 'alpha1234'})

    assert res.status_code == 200
    payload = res.get_json()
    assert payload['filename'] == 'alpha1234.txt'
    assert 'extraction world' in payload['text']


def test_upload_summarize_text(tmp_path, monkeypatch):
    monkeypatch.setattr(_files_mod, 'UPLOAD_DIR', str(tmp_path))
    content = (
        'This is a long test document about project planning. '
        'It includes milestones, task ownership, and risks. '
        'The intent is to verify summarization works for uploads. '
        'Extra sentence for length.'
    )
    (tmp_path / 'sum56789.txt').write_text(content, encoding='utf-8')

    client = app.test_client()
    res = client.post('/api/upload/summarize', json={'file_id': 'sum56789', 'max_chars': 140})

    assert res.status_code == 200
    payload = res.get_json()
    assert payload['filename'] == 'sum56789.txt'
    assert payload['summary']
    assert payload['summary_chars'] <= 140


def test_upload_search_matches_text(tmp_path, monkeypatch):
    monkeypatch.setattr(_files_mod, 'UPLOAD_DIR', str(tmp_path))
    (tmp_path / 'sea11111.txt').write_text('alpha beta gamma', encoding='utf-8')
    (tmp_path / 'sea22222.txt').write_text('beta only', encoding='utf-8')

    client = app.test_client()
    res = client.get('/api/upload/search?q=beta')

    assert res.status_code == 200
    payload = res.get_json()
    assert payload['count'] >= 2
    names = [row['filename'] for row in payload['results']]
    assert 'sea11111.txt' in names
    assert 'sea22222.txt' in names


class _FakeBrainIndex:
    def index_file(self, _path):
        return 3

    def get_stats(self):
        return {
            'files': [
                {'path': 'documents/a.txt', 'chunks': 2},
                {'path': 'documents/b.md', 'chunks': 1},
            ]
        }

    def remove_file(self, _path):
        return True


def test_brain_upload_batch(tmp_path, monkeypatch):
    monkeypatch.setattr(_files_mod, '_brain_dir_for_workspace', lambda: str(tmp_path))
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')

    import companion_ai.brain_index as brain_index_module
    monkeypatch.setattr(brain_index_module, 'get_brain_index', lambda: _FakeBrainIndex())

    client = app.test_client()
    res = client.post(
        '/api/brain/upload/batch',
        data={
            'folder': 'documents',
            'files': [
                (io.BytesIO(b'first doc'), 'a.txt'),
                (io.BytesIO(b'second doc'), 'b.md'),
            ],
        },
        headers={'X-API-TOKEN': 'secret'},
        content_type='multipart/form-data',
    )

    assert res.status_code == 200
    payload = res.get_json()
    assert payload['success'] is True
    assert payload['count'] == 2
    assert all(item['chunks_indexed'] == 3 for item in payload['uploaded'])


def test_brain_files_list(tmp_path, monkeypatch):
    monkeypatch.setattr(_files_mod, '_brain_dir_for_workspace', lambda: str(tmp_path))
    docs = tmp_path / 'documents'
    docs.mkdir(parents=True, exist_ok=True)
    (docs / 'a.txt').write_text('first', encoding='utf-8')
    (docs / 'b.md').write_text('# second', encoding='utf-8')

    import companion_ai.brain_index as brain_index_module
    monkeypatch.setattr(brain_index_module, 'get_brain_index', lambda: _FakeBrainIndex())

    client = app.test_client()
    res = client.get('/api/brain/files')

    assert res.status_code == 200
    payload = res.get_json()
    assert payload['count'] == 2
    names = [row['name'] for row in payload['files']]
    assert 'a.txt' in names
    assert 'b.md' in names


def test_brain_file_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(_files_mod, '_brain_dir_for_workspace', lambda: str(tmp_path))
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')
    docs = tmp_path / 'documents'
    docs.mkdir(parents=True, exist_ok=True)
    target = docs / 'gone.txt'
    target.write_text('bye', encoding='utf-8')

    import companion_ai.brain_index as brain_index_module
    monkeypatch.setattr(brain_index_module, 'get_brain_index', lambda: _FakeBrainIndex())

    client = app.test_client()
    denied = client.delete('/api/brain/file', json={'path': 'documents/gone.txt'})
    assert denied.status_code == 401

    ok = client.delete(
        '/api/brain/file',
        json={'path': 'documents/gone.txt'},
        headers={'X-API-TOKEN': 'secret'},
    )
    assert ok.status_code == 200
    assert ok.get_json()['deleted'] is True
    assert not target.exists()


def test_brain_extract_and_summarize(tmp_path, monkeypatch):
    monkeypatch.setattr(_files_mod, '_brain_dir_for_workspace', lambda: str(tmp_path))
    docs = tmp_path / 'documents'
    docs.mkdir(parents=True, exist_ok=True)
    target = docs / 'note.txt'
    target.write_text('This is a detailed knowledge note about project planning and coffee preferences.', encoding='utf-8')

    client = app.test_client()

    extract_res = client.post('/api/brain/extract', json={'path': 'documents/note.txt', 'max_chars': 200})
    assert extract_res.status_code == 200
    assert 'coffee preferences' in extract_res.get_json()['text']

    summary_res = client.post('/api/brain/summarize', json={'path': 'documents/note.txt', 'max_chars': 80})
    assert summary_res.status_code == 200
    assert summary_res.get_json()['summary']
