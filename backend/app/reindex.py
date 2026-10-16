"""Rebuild one document from its stored original without changing its identity."""
import asyncio
import sys
from uuid import UUID, uuid4

from qdrant_client import models
from . import main
from .text import chunks, extract


async def rebuild(ident):
    row = main.get_document(ident)
    if row['collection'] != main.COLLECTION:
        raise ValueError('Document belongs to another embedding model')
    parts = chunks(extract((main.DATA / (ident + row['suffix'])).read_bytes(), row['suffix']))
    if not parts or len(parts) > 2000:
        raise ValueError('Invalid document size')
    old_ids, offset = [], None
    while True:
        records, offset = await main.app.state.qdrant.scroll(main.COLLECTION, scroll_filter=main.document_filter([ident]), offset=offset, limit=100, with_payload=False, with_vectors=False)
        old_ids.extend(p.id for p in records)
        if offset is None:
            break
    points = []
    for start in range(0, len(parts), 16):
        batch = parts[start:start + 16]
        vectors = await main.embed([p['text'] for p in batch])
        if len(vectors) != len(batch):
            raise ValueError('Embedding count mismatch')
        points.extend(models.PointStruct(id=str(uuid4()), vector=v, payload={**p, 'document_id': ident, 'name': row['name']}) for p, v in zip(batch, vectors))
    try:
        for start in range(0, len(points), 16):
            await main.app.state.qdrant.upsert(main.COLLECTION, points=points[start:start + 16], wait=True)
    except Exception:
        await main.app.state.qdrant.delete(main.COLLECTION, points_selector=models.PointIdsList(points=[p.id for p in points]), wait=True)
        raise
    if old_ids:
        await main.app.state.qdrant.delete(main.COLLECTION, points_selector=models.PointIdsList(points=old_ids), wait=True)
    with main.db() as conn:
        conn.execute('UPDATE documents SET chunks = ? WHERE id = ?', (len(parts), ident))
    print(f'Reindexed {ident}: {len(parts)} chunks')


async def run():
    ident = str(UUID(sys.argv[1]))
    async with main.lifespan(main.app):
        await main.require_ready()
        await rebuild(ident)


if __name__ == '__main__':
    asyncio.run(run())
