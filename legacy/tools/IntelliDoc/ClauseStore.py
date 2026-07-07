from llama_index.core.storage.docstore import SimpleDocumentStore
from llama_index.core.storage.index_store import SimpleIndexStore


class ClauseStore:
    def __init__(self, domain):
        try:
            self.index_store = SimpleIndexStore.from_persist_dir(persist_dir=domain)
        except:
            self.index_store = SimpleIndexStore()
            self.index_store.persist(domain + "/index.json")

        try:
            self.doc_store = SimpleDocumentStore.from_persist_dir(persist_dir=domain)
        except:
            self.doc_store = SimpleDocumentStore()
            self.doc_store.persist(domain + "/docstore.json")
