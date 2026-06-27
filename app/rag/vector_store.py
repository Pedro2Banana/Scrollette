import chromadb

from app.config import RAG_COLLECTION, RAG_INDEX_DIR


class VectorStore:
    """Chroma-backed vector store for document chunks.

    Method signatures stay Chroma-agnostic so the backend can later be swapped
    (e.g. sqlite-vec) without touching callers. We pass our own embeddings, so
    Chroma never loads its default embedding model.
    """

    def __init__(self, path=RAG_INDEX_DIR, collection=RAG_COLLECTION):
        self._client = chromadb.PersistentClient(path=str(path))
        self._collection = self._client.get_or_create_collection(
            name=collection, metadata={"hnsw:space": "cosine"}
        )

    def upsert(self, chunks, vectors, document_id):
        """Insert/overwrite a document's chunks. id = document:page:chunk so the
        same chunk re-indexes idempotently."""
        ids = [f"{document_id}:{c.page_number}:{c.chunk_index}" for c in chunks]
        metadatas = [
            {
                "document_id": document_id,
                "page_number": c.page_number,
                "chunk_index": c.chunk_index,
            }
            for c in chunks
        ]
        documents = [c.text for c in chunks]
        self._collection.upsert(
            ids=ids, embeddings=vectors, documents=documents, metadatas=metadatas
        )

    def query(self, vector, k=5, where=None):
        """Return up to k nearest chunks as dicts {text, page_number, distance}."""
        result = self._collection.query(
            query_embeddings=[vector], n_results=k, where=where
        )
        hits = []
        for text, meta, distance in zip(
            result["documents"][0], result["metadatas"][0], result["distances"][0]
        ):
            hits.append(
                {
                    "text": text,
                    "page_number": meta["page_number"],
                    "distance": distance,
                }
            )
        return hits

    def has_page(self, document_id, page_number):
        """Whether this page already has chunks indexed (skip re-embedding)."""
        found = self._collection.get(
            where={
                "$and": [
                    {"document_id": document_id},
                    {"page_number": page_number},
                ]
            },
            limit=1,
        )
        return bool(found["ids"])

    def delete_document(self, document_id):
        self._collection.delete(where={"document_id": document_id})

    def count(self):
        return self._collection.count()
