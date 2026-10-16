"""Run against a live Docker stack: python scripts/smoke.py (models required)."""
from pathlib import Path
import httpx
import time

with httpx.Client(base_url='http://127.0.0.1:3000', timeout=300) as client:
    ready = client.get('/api/health/ready')
    ready.raise_for_status()
    print('Readiness:', ready.json())
    sample = Path(__file__).resolve().parents[1] / 'samples' / 'docker-notes.md'
    response = client.post('/api/documents', files={'file': (sample.name, sample.read_bytes(), 'text/markdown')})
    response.raise_for_status()
    document = response.json()
    print('Uploaded:', document)
    try:
        for _ in range(120):
            state = client.get('/api/documents/' + document['id']).json()
            if state['status'] == 'ready':
                break
            assert state['status'] != 'failed', state
            time.sleep(2)
        else:
            raise AssertionError('Document processing timed out')
        chat = client.post('/api/conversations').json()
        response = client.post('/api/chat', json={'question': 'Belgeler hangi volume içinde saklanıyor?', 'document_ids': [document['id']], 'conversation_id': chat['id']})
        response.raise_for_status()
        result = response.json()
        assert result['answer'] and result['sources'], result
        assert all(s['document_id'] == document['id'] for s in result['sources'])
        print('Answer:', result['answer'])
        print('Source count:', len(result['sources']))
        another = client.post('/api/conversations').json()
        saved = client.get('/api/conversations/' + chat['id']).json()
        assert len(saved['messages']) == 2 and another['messages'] == []
        print('Conversation preserved:', chat['id'])
        original = client.get('/api/documents/' + document['id'] + '/file')
        assert original.content == sample.read_bytes()
    finally:
        response = client.delete('/api/documents/' + document['id'])
        response.raise_for_status()
    assert client.get('/api/documents/' + document['id'] + '/file').status_code == 404
    print('PASS: live upload, retrieval, generation, download and delete')
