from rag.vector_store import VectorStore

class RagRepository:
    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store

    def collection_exists(self, collection_name: str) -> bool:
        """Check if a specific course collection exists in ChromaDB."""
        return self.vector_store.collection_exists(collection_name)

    def delete_collection(self, collection_name: str) -> None:
        """Delete an entire course collection from ChromaDB."""
        self.vector_store.delete_collection(collection_name)