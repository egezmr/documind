import asyncio
import logging
from celery.signals import worker_ready
from .queue import celery


@worker_ready.connect
def recover_pending(sender, **kwargs):
    from . import main
    # Redelivery may duplicate a broker message; ready-state checks and stable
    # point IDs make execution idempotent with the single worker configuration.
    with main.db() as conn:
        ids = [r['id'] for r in conn.execute("SELECT id FROM documents WHERE status IN ('queued','processing','retrying') AND collection=?", (main.COLLECTION,))]
    for ident in ids:
        celery.send_task('documind.index_document', args=[ident])


@celery.task(bind=True, name='documind.index_document', max_retries=3)
def index_document(self, ident):
    from . import main

    async def run():
        async with main.lifespan(main.app):
            await main.process_document(ident)
    try:
        asyncio.run(run())
    except ValueError as exc:
        main.set_document_state(ident, 'failed', error=str(exc))
    except Exception as exc:
        logging.exception('Document indexing failed: %s', ident)
        exhausted = self.request.retries >= self.max_retries
        main.set_document_state(ident, 'failed' if exhausted else 'retrying', error='Servis bağlantısı kurulamadı. Yeniden deneyebilirsiniz.' if exhausted else 'Geçici servis hatası; otomatik yeniden denenecek.')
        if not exhausted:
            raise self.retry(exc=exc, countdown=10 * (2 ** self.request.retries))
