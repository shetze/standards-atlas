from llama_index.core.schema import NodeWithScore, RelatedNodeInfo
from llama_index.core.indices import VectorStoreIndex
from llama_index.core.storage import StorageContext


class IngestedDoc:
    def __init__(self,doc_id,doc_metadata):
        self.doc_id = doc_id
        self.doc_metadata = doc_metadata

class Chunk:
    def __init__(self, score, document, text):
        self.score = score
        self.document = document
        self.text = text

    def __str__(self):
        return f"score: {self.score}\nmeta: {self.document.doc_metadata}\ntext:\n{self.text}\n"

    @classmethod
    def from_node(cls, node):
        doc_id = node.node.ref_doc_id if node.node.ref_doc_id is not None else "-"
        return cls(
                score=node.score or 0.0,
                document=IngestedDoc(
                    doc_id=doc_id,
                    doc_metadata=node.metadata,
                    ),
                text=node.get_content(),
                )

class ClauseRetriever:
    hits={}
    misses={}
    avg_hits={}
    avg_misses={}
    def __init__(self, llm, vectorstore, embedding_engine, clausestore, domain):
        self.llm = llm
        self.embedding_engine = embedding_engine
        self.embed_model = embedding_engine.embedding_service
        self.vectorstore = vectorstore
        self.clausestore = clausestore
        self.domain = domain
        self.show_progress = True

        self.storage_context = StorageContext.from_defaults(
                vector_store=vectorstore.vector_store,
                docstore=clausestore.doc_store,
                index_store=clausestore.index_store,
                persist_dir=domain,
                )

    def _get_sibling_nodes_text( self, node, width, forward = True):
        explored_nodes_texts = []
        current_node = node.node
        for _ in range(width):
            explored_node_info: RelatedNodeInfo | None = (
                current_node.next_node if forward else current_node.prev_node
            )
            if explored_node_info is None:
                break

            explored_node = self.storage_context.docstore.get_node(
                explored_node_info.node_id
            )

            explored_nodes_texts.append(explored_node.get_content())
            current_node = explored_node

        return explored_nodes_texts


    def retrieve(self, text, limit, width):
        index = VectorStoreIndex.from_vector_store(
                    self.vectorstore.vector_store,
                    storage_context=self.storage_context,
                    store_nodes_override=True,
                    show_progress=self.show_progress,
                    embed_model=self.embed_model,
                    )
        vector_index_retriever = self.vectorstore.get_retriever( index=index, similarity_top_k=limit )
        nodes = vector_index_retriever.retrieve(text)
        nodes.sort(key=lambda n: n.score or 0.0, reverse=True)
        retrieved_nodes = []
        for node in nodes:
            chunk = Chunk.from_node(node)
            chunk.previous_texts = self._get_sibling_nodes_text(
                    node, width, False
                    )
            chunk.next_texts = self._get_sibling_nodes_text(node, width)
            retrieved_nodes.append(chunk)
        return retrieved_nodes

