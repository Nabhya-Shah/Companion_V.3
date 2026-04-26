# companion_ai/web/files_routes.py
"""Files blueprint — file upload/list/extract/summarize/search + brain knowledge base."""

import os
import logging
from pathlib import Path
from datetime import datetime

from flask import Blueprint, request, jsonify, send_from_directory

from companion_ai.core import config as core_config
from companion_ai.agents.vision import vision_manager
from companion_ai.web import state

logger = logging.getLogger(__name__)

files_bp = Blueprint('files', __name__)

# --- Upload constants ---

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
UPLOAD_DIR = os.path.join(DATA_DIR, 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'docx', 'txt', 'md'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


# --- Upload helpers ---

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _resolve_uploaded_file_path(file_id: str) -> str | None:
    for ext in ALLOWED_EXTENSIONS:
        candidate = os.path.join(UPLOAD_DIR, f"{file_id}.{ext}")
        if os.path.exists(candidate):
            return candidate
    return None


def _extract_text_from_uploaded_path(file_path: str, max_chars: int = 12000) -> tuple[str, bool]:
    ext = os.path.splitext(file_path)[1].lower()
    content = ''

    try:
        if ext in {'.txt', '.md'}:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        elif ext == '.pdf':
            try:
                import pypdf
                with open(file_path, 'rb') as f:
                    reader = pypdf.PdfReader(f)
                    pages = []
                    for page in reader.pages[:10]:
                        pages.append((page.extract_text() or '').strip())
                    content = '\n\n'.join([p for p in pages if p])
            except Exception:
                content = ''
        elif ext == '.docx':
            try:
                from docx import Document
                doc = Document(file_path)
                content = '\n'.join([p.text for p in doc.paragraphs if p.text.strip()])
            except Exception:
                content = ''
    except Exception:
        content = ''

    content = (content or '').strip()
    if not content:
        return '', False
    if len(content) > max_chars:
        return content[:max_chars], True
    return content, False


def _summarize_text_simple(text: str, max_chars: int = 600) -> str:
    if not text:
        return ''
    cleaned = ' '.join(text.replace('\r', ' ').replace('\n', ' ').split())
    if len(cleaned) <= max_chars:
        return cleaned

    sentence_candidates = cleaned.replace('?', '.').replace('!', '.').split('.')
    out = []
    total = 0
    for raw in sentence_candidates:
        sentence = raw.strip()
        if not sentence:
            continue
        addition = (sentence + '. ')
        if total + len(addition) > max_chars:
            break
        out.append(addition)
        total += len(addition)
        if len(out) >= 4:
            break
    if out:
        return ''.join(out).strip()
    return cleaned[:max_chars].rstrip() + '...'


def _save_uploaded_file(file, analyze_images: bool = True):
    import uuid as _uuid

    if not file or not file.filename:
        return None, {'success': False, 'error': 'No file selected'}, 400
    if not allowed_file(file.filename):
        return None, {'success': False, 'error': f'File type not allowed. Allowed: {", ".join(sorted(ALLOWED_EXTENSIONS))}'}, 400

    file_id = str(_uuid.uuid4())[:8]
    ext = file.filename.rsplit('.', 1)[1].lower()
    safe_filename = f"{file_id}.{ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)

    file.save(file_path)
    file_size = os.path.getsize(file_path)
    if file_size > MAX_FILE_SIZE:
        os.remove(file_path)
        return None, {'success': False, 'error': 'File too large (max 10MB)'}, 400

    is_image = ext in {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    is_pdf = ext == 'pdf'
    is_doc = ext in {'docx', 'txt'}

    analysis = None
    if analyze_images and is_image:
        try:
            analysis = vision_manager.analyze_image_file(
                file_path,
                prompt="DESCRIBE ONLY - don't solve or interpret. Just describe what you see: text, numbers, objects, layout. If there's math/text, transcribe it exactly. Let someone else solve it."
            )
            logger.info(f"Image analyzed: {file_id} - {analysis[:100]}...")
        except Exception as e:
            logger.error(f"Image analysis failed: {e}")

    payload = {
        'success': True,
        'file_id': file_id,
        'filename': file.filename,
        'type': 'image' if is_image else 'pdf' if is_pdf else 'document' if is_doc else 'file',
        'size': file_size,
        'url': f'/api/upload/{file_id}',
        'analysis': analysis,
    }

    # Auto-index uploaded documents into brain index for unified search
    if not is_image:
        try:
            from companion_ai.brain import get_brain_index
            index = get_brain_index()
            store_path = f"uploads/{safe_filename}"
            chunks = index.index_file(Path(file_path), store_path=store_path)
            if chunks:
                logger.info(f"Auto-indexed upload {safe_filename}: {chunks} chunks")
                payload['indexed'] = True
                payload['chunks'] = chunks
        except Exception as e:
            logger.warning(f"Auto-index failed for {safe_filename}: {e}")

    return payload, None, 200


# --- Upload routes ---

@files_bp.route('/api/upload', methods=['POST'])
def upload_file():
    """Upload a file and optionally analyze it with vision."""
    blocked = state.enforce_feature_permission('files_upload')
    if blocked:
        return blocked
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    payload, err, status = _save_uploaded_file(request.files['file'], analyze_images=True)
    if err:
        return jsonify(err), status
    return jsonify(payload)


@files_bp.route('/api/upload/batch', methods=['POST'])
def upload_files_batch():
    """Upload multiple files in one request."""
    blocked = state.enforce_feature_permission('files_upload')
    if blocked:
        return blocked
    files = request.files.getlist('files')
    if not files and 'file' in request.files:
        files = [request.files['file']]
    if not files:
        return jsonify({'success': False, 'error': 'No files provided'}), 400

    uploaded = []
    errors = []
    for file in files:
        payload, err, status = _save_uploaded_file(file, analyze_images=True)
        if payload:
            uploaded.append(payload)
        else:
            errors.append({
                'filename': getattr(file, 'filename', ''),
                'error': (err or {}).get('error', 'Upload failed'),
                'status': status,
            })

    status_code = 200 if uploaded else 400
    return jsonify({
        'success': bool(uploaded),
        'count': len(uploaded),
        'uploaded': uploaded,
        'errors': errors,
    }), status_code


@files_bp.route('/api/upload/list', methods=['GET'])
def list_uploaded_files():
    """List recently uploaded files with basic metadata."""
    limit = max(1, min(int(request.args.get('limit', 50) or 50), 200))
    rows = []
    for name in os.listdir(UPLOAD_DIR):
        path = os.path.join(UPLOAD_DIR, name)
        if not os.path.isfile(path) or '.' not in name:
            continue
        file_id, ext = name.rsplit('.', 1)
        ext = ext.lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue
        stat = os.stat(path)
        rows.append({
            'file_id': file_id,
            'filename': name,
            'ext': ext,
            'size': stat.st_size,
            'url': f'/api/upload/{file_id}',
            'modified_at': datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    rows.sort(key=lambda x: x['modified_at'], reverse=True)
    return jsonify({'files': rows[:limit], 'count': min(len(rows), limit)})


@files_bp.route('/api/upload/<file_id>', methods=['GET'])
def get_uploaded_file(file_id):
    """Serve an uploaded file."""
    for ext in ALLOWED_EXTENSIONS:
        filename = f"{file_id}.{ext}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        if os.path.exists(filepath):
            return send_from_directory(UPLOAD_DIR, filename)
    return jsonify({'error': 'File not found'}), 404


@files_bp.route('/api/upload/extract', methods=['POST'])
def extract_uploaded_file_text():
    data = request.get_json(silent=True) or {}
    file_id = str(data.get('file_id') or '').strip()
    if not file_id:
        return jsonify({'error': 'file_id is required'}), 400

    max_chars = max(500, min(int(data.get('max_chars') or 12000), 50000))
    file_path = _resolve_uploaded_file_path(file_id)
    if not file_path:
        return jsonify({'error': 'File not found'}), 404

    text, truncated = _extract_text_from_uploaded_path(file_path, max_chars=max_chars)
    if not text:
        return jsonify({'error': 'No extractable text for this file type'}), 400

    return jsonify({
        'file_id': file_id,
        'filename': os.path.basename(file_path),
        'chars': len(text),
        'truncated': truncated,
        'text': text,
    })


@files_bp.route('/api/upload/summarize', methods=['POST'])
def summarize_uploaded_file_text():
    data = request.get_json(silent=True) or {}
    file_id = str(data.get('file_id') or '').strip()
    if not file_id:
        return jsonify({'error': 'file_id is required'}), 400

    max_chars = max(120, min(int(data.get('max_chars') or 700), 3000))
    file_path = _resolve_uploaded_file_path(file_id)
    if not file_path:
        return jsonify({'error': 'File not found'}), 404

    text, _ = _extract_text_from_uploaded_path(file_path, max_chars=20000)
    if not text:
        return jsonify({'error': 'No extractable text for this file type'}), 400

    summary = _summarize_text_simple(text, max_chars=max_chars)
    return jsonify({
        'file_id': file_id,
        'filename': os.path.basename(file_path),
        'source_chars': len(text),
        'summary_chars': len(summary),
        'summary': summary,
    })


@files_bp.route('/api/upload/search', methods=['GET'])
def search_uploaded_files():
    query = (request.args.get('q') or '').strip().lower()
    if not query:
        return jsonify({'error': 'q is required'}), 400

    limit = max(1, min(int(request.args.get('limit') or 20), 100))
    results = []

    for name in os.listdir(UPLOAD_DIR):
        path = os.path.join(UPLOAD_DIR, name)
        if not os.path.isfile(path) or '.' not in name:
            continue
        file_id, ext = name.rsplit('.', 1)
        ext = ext.lower()
        if ext not in {'txt', 'md', 'pdf', 'docx'}:
            continue

        text, _ = _extract_text_from_uploaded_path(path, max_chars=15000)
        if not text:
            continue
        low = text.lower()
        score = low.count(query)
        if score <= 0:
            continue

        idx = low.find(query)
        start = max(0, idx - 80)
        end = min(len(text), idx + len(query) + 140)
        snippet = text[start:end].replace('\n', ' ').strip()
        stat = os.stat(path)
        results.append({
            'file_id': file_id,
            'filename': name,
            'score': score,
            'snippet': snippet,
            'modified_at': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'url': f'/api/upload/{file_id}',
        })

    results.sort(key=lambda x: (x['score'], x['modified_at']), reverse=True)
    return jsonify({'query': query, 'count': min(len(results), limit), 'results': results[:limit]})


# --- Brain helpers ---

def _brain_dir_for_workspace() -> str:
    workspace_key = state._resolve_workspace_key()
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'BRAIN')
    if workspace_key and workspace_key != 'default':
        return os.path.join(base, 'workspaces', workspace_key)
    return base


def _resolve_brain_file_path(relative_path: str) -> str | None:
    safe_relative = str(relative_path or '').replace('\\', '/').lstrip('/').strip()
    if not safe_relative or '..' in safe_relative.split('/'):
        return None
    root = os.path.abspath(_brain_dir_for_workspace())
    candidate = os.path.abspath(os.path.join(root, safe_relative))
    if not candidate.startswith(root):
        return None
    return candidate


def _save_brain_file(file, target_dir: str, subfolder: str, index):
    from werkzeug.utils import secure_filename

    filename = secure_filename(file.filename)
    if not filename:
        return None, {'filename': file.filename, 'error': 'Invalid filename'}

    filepath = os.path.join(target_dir, filename)
    if os.path.exists(filepath):
        base, ext = os.path.splitext(filename)
        suffix = datetime.now().strftime('%Y%m%d%H%M%S')
        filename = f"{base}_{suffix}{ext}"
        filepath = os.path.join(target_dir, filename)

    file.save(filepath)
    chunks = index.index_file(Path(filepath))
    logger.info(f"Uploaded to brain: {filename} ({chunks} chunks indexed)")
    return {
        'success': True,
        'filename': filename,
        'path': f"{subfolder}/{filename}",
        'chunks_indexed': chunks,
    }, None


# --- Brain routes ---

@files_bp.route('/api/brain/upload', methods=['POST'])
def brain_upload():
    """Upload a file to the brain folder and index it."""
    blocked = state.enforce_feature_permission('files_upload')
    if blocked:
        return blocked
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    subfolder = request.form.get('folder', 'documents')
    target_dir = os.path.join(_brain_dir_for_workspace(), subfolder)
    os.makedirs(target_dir, exist_ok=True)

    try:
        from werkzeug.utils import secure_filename
        from companion_ai.brain import get_brain_index

        filename = secure_filename(file.filename)
        filepath = os.path.join(target_dir, filename)
        file.save(filepath)

        index = get_brain_index()
        chunks = index.index_file(Path(filepath))

        logger.info(f"Uploaded to brain: {filename} ({chunks} chunks indexed)")

        return jsonify({
            'success': True,
            'filename': filename,
            'path': f"{subfolder}/{filename}",
            'chunks_indexed': chunks,
        })
    except Exception as e:
        logger.error(f"Brain upload error: {e}")
        return jsonify({'error': str(e)}), 500


@files_bp.route('/api/brain/upload/batch', methods=['POST'])
def brain_upload_batch():
    """Upload and index multiple files for the brain workspace."""
    blocked = state.enforce_feature_permission('files_upload')
    if blocked:
        return blocked
    files = request.files.getlist('files')
    if not files and 'file' in request.files:
        files = [request.files['file']]
    if not files:
        return jsonify({'error': 'No files provided'}), 400

    subfolder = request.form.get('folder', 'documents')
    target_dir = os.path.join(_brain_dir_for_workspace(), subfolder)
    os.makedirs(target_dir, exist_ok=True)

    try:
        from companion_ai.brain import get_brain_index
        index = get_brain_index()
        uploaded = []
        errors = []
        for file in files:
            if not file or not file.filename:
                errors.append({'filename': '', 'error': 'No file selected'})
                continue
            payload, err = _save_brain_file(file, target_dir, subfolder, index)
            if payload:
                uploaded.append(payload)
            elif err:
                errors.append(err)

        status_code = 200 if uploaded else 400
        return jsonify({
            'success': bool(uploaded),
            'count': len(uploaded),
            'uploaded': uploaded,
            'errors': errors,
        }), status_code
    except Exception as e:
        logger.error(f"Brain batch upload error: {e}")
        return jsonify({'error': str(e)}), 500


@files_bp.route('/api/brain/stats', methods=['GET'])
def brain_stats():
    """Get brain index statistics."""
    try:
        from companion_ai.brain import get_brain_index
        index = get_brain_index()
        stats = index.get_stats()
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Brain stats error: {e}")
        return jsonify({'error': str(e)}), 500


@files_bp.route('/api/brain/files', methods=['GET'])
def brain_files_list():
    """List workspace brain files with index metadata."""
    try:
        root = _brain_dir_for_workspace()
        root_path = Path(root)
        if not root_path.exists():
            return jsonify({'files': [], 'count': 0})

        from companion_ai.brain import get_brain_index
        index = get_brain_index()
        stats = index.get_stats()
        chunk_map = {
            str(item.get('path', '')).replace('\\', '/'): int(item.get('chunks', 0))
            for item in (stats.get('files') or [])
            if item.get('path')
        }

        files = []
        for path in root_path.rglob('*'):
            if not path.is_file():
                continue
            rel = str(path.relative_to(root_path)).replace('\\', '/')
            stat = path.stat()
            files.append({
                'path': rel,
                'name': path.name,
                'size': stat.st_size,
                'modified_at': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'chunks': chunk_map.get(rel, 0),
            })

        files.sort(key=lambda row: row['modified_at'], reverse=True)
        return jsonify({'files': files, 'count': len(files)})
    except Exception as e:
        logger.error(f"Brain files list error: {e}")
        return jsonify({'error': str(e)}), 500


@files_bp.route('/api/brain/extract', methods=['POST'])
def brain_extract_text():
    """Extract text from a brain workspace file."""
    data = request.get_json(silent=True) or {}
    rel = str(data.get('path') or '').strip()
    if not rel:
        return jsonify({'error': 'path is required'}), 400

    max_chars = max(500, min(int(data.get('max_chars') or 12000), 50000))
    abs_path = _resolve_brain_file_path(rel)
    if not abs_path or not os.path.exists(abs_path):
        return jsonify({'error': 'File not found'}), 404

    text, truncated = _extract_text_from_uploaded_path(abs_path, max_chars=max_chars)
    if not text:
        return jsonify({'error': 'No extractable text for this file type'}), 400

    return jsonify({
        'path': rel.replace('\\', '/'),
        'filename': os.path.basename(abs_path),
        'chars': len(text),
        'truncated': truncated,
        'text': text,
    })


@files_bp.route('/api/brain/summarize', methods=['POST'])
def brain_summarize_text():
    """Summarize text from a brain workspace file."""
    data = request.get_json(silent=True) or {}
    rel = str(data.get('path') or '').strip()
    if not rel:
        return jsonify({'error': 'path is required'}), 400

    max_chars = max(120, min(int(data.get('max_chars') or 700), 3000))
    abs_path = _resolve_brain_file_path(rel)
    if not abs_path or not os.path.exists(abs_path):
        return jsonify({'error': 'File not found'}), 404

    text, _ = _extract_text_from_uploaded_path(abs_path, max_chars=20000)
    if not text:
        return jsonify({'error': 'No extractable text for this file type'}), 400

    summary = _summarize_text_simple(text, max_chars=max_chars)
    return jsonify({
        'path': rel.replace('\\', '/'),
        'filename': os.path.basename(abs_path),
        'source_chars': len(text),
        'summary_chars': len(summary),
        'summary': summary,
    })


@files_bp.route('/api/brain/file', methods=['DELETE'])
def brain_file_delete():
    """Delete one brain file and its indexed chunks."""
    blocked = state.enforce_feature_permission('files_upload')
    if blocked:
        return blocked
    data = request.get_json(silent=True) or {}
    rel = data.get('path')
    if not rel:
        return jsonify({'error': 'path is required'}), 400

    abs_path = _resolve_brain_file_path(rel)
    if not abs_path:
        return jsonify({'error': 'Invalid path'}), 400
    if not os.path.exists(abs_path):
        return jsonify({'error': 'File not found'}), 404

    try:
        os.remove(abs_path)
        normalized = str(rel).replace('\\', '/').lstrip('/')
        from companion_ai.brain import get_brain_index
        index = get_brain_index()
        index.remove_file(normalized)
        return jsonify({'deleted': True, 'path': normalized})
    except Exception as e:
        logger.error(f"Brain file delete error: {e}")
        return jsonify({'error': str(e)}), 500


@files_bp.route('/api/brain/reindex', methods=['POST'])
def brain_reindex():
    """Trigger full reindex of brain folder."""
    blocked = state.enforce_feature_permission('files_upload')
    if blocked:
        return blocked
    try:
        os.environ['BRAIN_DIR'] = _brain_dir_for_workspace()
        from companion_ai.brain import get_brain_index
        index = get_brain_index()
        results = index.index_all()
        return jsonify({
            'success': True,
            'files_indexed': len(results),
            'total_chunks': sum(results.values()),
            'files': results,
        })
    except Exception as e:
        logger.error(f"Brain reindex error: {e}")
        return jsonify({'error': str(e)}), 500


@files_bp.route('/api/brain/search', methods=['GET'])
def brain_search_api():
    """Search brain documents via API."""
    query = request.args.get('q', '')
    if not query:
        return jsonify({'error': 'No query provided'}), 400

    try:
        from companion_ai.brain import get_brain_index
        index = get_brain_index()
        results = index.search(query, limit=10)
        return jsonify({'query': query, 'results': results})
    except Exception as e:
        logger.error(f"Brain search error: {e}")
        return jsonify({'error': str(e)}), 500
