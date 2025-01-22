from llama_index.embeddings.ollama import OllamaEmbedding


class Embedding:
    def __init__(self, index, embedding):
        self.index = index
        self.embedding = embedding


class EmbeddingEngine:
    # def __init__(self, model="mxbai-embed-large", url="http://localhost:11434"):
    def __init__(self, model="nomic-embed-text", url="http://localhost:11434"):
    # def __init__(self, model="paraphrase-multilingual", url="http://localhost:11434"):
        self.embedding_service = OllamaEmbedding(model_name=model, base_url=url)
        self.model = model

    def texts_to_vector(self, texts):
        embeddings = self.embedding_service.get_text_embedding_batch(texts)
        return [
            Embedding(index=texts_embeddings.index(embedding), embedding=embedding)
            for embedding in embeddings
        ]
