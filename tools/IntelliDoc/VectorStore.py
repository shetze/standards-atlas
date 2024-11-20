


from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

class VectorStore:
    def __init__(self, domain, vectorDB = 'qdrant.db'):
        client = QdrantClient(path=domain+'/'+vectorDB)
        self.vector_store = QdrantVectorStore(
                client = client,
                collection_name=domain
                )
