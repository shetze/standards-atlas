import tempfile
from pathlib import Path
from llama_index.readers.file.markdown import MarkdownReader
from llama_index.core.schema import Document
from llama_index.core.node_parser import MarkdownNodeParser, SentenceWindowNodeParser
from llama_index.core.indices import VectorStoreIndex, load_index_from_storage
from llama_index.core.storage import StorageContext


class BaseIngestor:
    def __init__(self, storage_context, embed_model, transformations, domain):
        self.storage_context = storage_context
        self.embed_model = embed_model
        self.transformations = transformations
        self.show_progress = True
        self.domain = domain
        self._index = self._initialize_index()

    def _initialize_index(self):
        try:
            index = load_index_from_storage(
                    storage_context=self.storage_context,
                    store_nodes_override=True,
                    show_progress=self.show_progress,
                    embed_model=self.embed_model,
                    transformations=self.transformations,
                    )
        except ValueError:
            index = VectorStoreIndex.from_documents(
                    [],
                    storage_context=self.storage_context,
                    store_nodes_override=True,
                    show_progress=self.show_progress,
                    embed_model=self.embed_model,
                    transformations=self.transformations,
                    )
            index.storage_context.persist(persist_dir=self.domain)
        return index

    def _save_index(self):
        self._index.storage_context.persist(persist_dir=self.domain)

    def ingest_documents(self, documents):
        for document in documents:
            self._index.insert(document)
        self._save_index()
        return documents

class ClauseIngestor:
    @staticmethod
    def _clause_to_documents(clause):
        docSeries=clause.structure.docSeries
        clauseID=clause.structure.ID
        text=clause.getText()
        clauseType=clause.clauseType()
        heading=clause.heading.getBestHeading()
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            try:
                path_to_tmp = Path(tmp.name)
                if isinstance(text, bytes):
                    path_to_tmp.write_bytes(text)
                else:
                    path_to_tmp.write_text(text)
                documents = MarkdownReader().load_data(path_to_tmp)
                for i in range(len(documents)):
                    documents[i].text = documents[i].text.replace("\u0000", "")
                    documents[i].metadata["doc_id"] = documents[i].doc_id
                    documents[i].excluded_embed_metadata_keys = ["doc_id"]
                    documents[i].excluded_llm_metadata_keys = ["file_name", "doc_id", "page_label"]
                    documents[i].metadata["series"] = docSeries
                    documents[i].metadata["clause"] = clauseID
                    documents[i].metadata["type"] = clauseType
                    documents[i].metadata["heading"] = heading
                return documents
            finally:
                tmp.close()
                path_to_tmp.unlink()

    def __init__(self, llm, vectorstore, embedding_engine, clausestore, domain):
        self.llm = llm
        self.storage_context = StorageContext.from_defaults(
                vector_store=vectorstore.vector_store,
                docstore=clausestore.doc_store,
                index_store=clausestore.index_store,
                persist_dir=domain,
                )
        # node_parser = MarkdownNodeParser.from_defaults(include_metadata = False, include_prev_next_rel = True)
        node_parser = SentenceWindowNodeParser.from_defaults()
        self.ingestor = BaseIngestor(
                self.storage_context,
                embed_model=embedding_engine.embedding_service,
                transformations=[node_parser, embedding_engine.embedding_service],
                domain = domain
                )

    def ingest_clause(self, clause):
        documents = self._clause_to_documents(clause)
        return self.ingestor.ingest_documents(documents)

