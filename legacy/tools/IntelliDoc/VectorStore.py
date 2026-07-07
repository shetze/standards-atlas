from llama_index.core.indices.vector_store import VectorIndexRetriever, VectorStoreIndex
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient


class VectorStore:
    def __init__(self, domain, vectorDB="qdrant.db"):
        client = QdrantClient(path=domain + "/" + vectorDB)
        self.vector_store = QdrantVectorStore(client=client, collection_name=domain)

    def get_retriever(self, index, similarity_top_k=2):
        return VectorIndexRetriever(
            index=index,
            similarity_top_k=similarity_top_k,
            doc_ids=None,
            filters=(None),
        )
