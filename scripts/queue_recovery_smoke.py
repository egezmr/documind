"""Local integration test: briefly stops the named worker and restarts Redis.

Run only on the local DocuMind development stack, with no active uploads.
"""
import subprocess
import time
import httpx


def compose(*args):
    subprocess.run(['docker', 'compose', *args], check=True)


ident = None
with httpx.Client(base_url='http://127.0.0.1:3000', timeout=30) as client:
    try:
        compose('stop', 'document-worker')
        response = client.post('/api/documents', files={'file': ('queue-recovery.txt', b'Queue recovery test: Docker isolates services.')})
        response.raise_for_status()
        ident = response.json()['id']
        state = client.get('/api/documents/' + ident).json()
        assert state['status'] == 'queued', state
        assert client.get('/api/health/live').status_code == 200
        time.sleep(2)  # Redis appendfsync everysec durability boundary.
        compose('restart', 'redis-service')
        compose('up', '-d', 'document-worker')
        for _ in range(120):
            response = client.get('/api/documents/' + ident)
            response.raise_for_status()
            state = response.json()
            if state['status'] == 'ready':
                break
            assert state['status'] != 'failed', state
            time.sleep(2)
        else:
            raise AssertionError('Recovery timed out')
        assert state['chunks'] == 1
        response = client.delete('/api/documents/' + ident)
        response.raise_for_status()
        print('PASS: API responsive while worker stopped; queued document processed after Redis/worker restart')
    finally:
        compose('start', 'document-worker')
