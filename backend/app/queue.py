import os
from celery import Celery

celery = Celery('documind', broker=os.getenv('REDIS_URL', 'redis://redis-service:6379/0'), include=['app.tasks'])
celery.conf.update(
    task_serializer='json', accept_content=['json'], task_ignore_result=True,
    task_acks_late=True, task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1, broker_connection_retry_on_startup=True,
    broker_transport_options={'visibility_timeout': 3600, 'socket_connect_timeout': 3, 'socket_timeout': 3},
    broker_connection_timeout=3,
    task_publish_retry=False,
)


async def enqueue(ident):
    import asyncio
    await asyncio.to_thread(celery.send_task, 'documind.index_document', args=[ident])
