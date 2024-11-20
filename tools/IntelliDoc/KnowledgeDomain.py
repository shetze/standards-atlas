from llama_index.core.schema import Document
from IntelliDoc.Clause import Clause, ClauseID, ClauseHeading
from IntelliDoc.LLM import LLM
from IntelliDoc.VectorStore import VectorStore
from IntelliDoc.Embedding import EmbeddingEngine
from IntelliDoc.ClauseStore import ClauseStore
from IntelliDoc.ClauseIngestor import ClauseIngestor

class DocTree():
    chapterIndex = None
    def __init__(self, documents):
        self.documents = documents
        self.misses = 0
        if DocTree.chapterIndex == None:
            DocTree.chapterIndex = {}
            for docType in self.documents.keys():
                for docSeries in self.documents[docType].keys():
                    DocTree.chapterIndex[docSeries] = {} 

    def addRootClause(self, domain, clause, rootID):
        docType = clause.docType()
        if not docType in self.documents.keys():
            logger.warning(f'unexpected new docType for {clause}')
            self.documents[docType]={}
        docSeries = clause.docSeries()
        rootTitle = f"Root Clause for {rootID}"
        linkClause = None
        if not docSeries in self.documents[docType].keys() or self.documents[docType][docSeries] == None:
            rootClause = Clause(rootID, rootTitle, clauseType='x', domain=domain)
            rootClause.structure.seriesPart = 'rootClause'
            self.documents[docType][docSeries] = rootClause
            Clause.clauseIndex[docSeries] = rootClause
        if clause.multipartSeries():
            part = clause.seriesPart()
            partTitle = f"Part {part} Clause for {rootID}"
            partClauseID = rootID+"-"+part
            rootClause = self.documents[docType][docSeries]
            if not rootClause.hasSubClauseRef(partClauseID):
                partClause = Clause(partClauseID, partTitle, clauseType='x', domain=domain)
                partClause.structure.seriesPart = 'partRoot'
                Clause.clauseIndex[partClauseID] = partClause
                partClause.addSubClauseRef(clause.id())
                rootClause.addSubClauseRef(partClauseID)
            else:
                partClause = Clause.clauseIndex[partClauseID]
                partClause.addSubClauseRef(clause.id())
        else:
            rootClause = self.documents[docType][docSeries]
            if not rootClause.hasSubClauseRef(clause.id()):
                rootClause.addSubClauseRef(clause.id())

    def listDocsInTree(self):
        docsList = []
        for docType in self.documents.keys():
            for docSeries in self.documents[docType].keys():
                docRoot = self.documents[docType][docSeries]
                docsList.append(docRoot.id())
        return docsList

    def docSeriesWeight(self):
        docsWeight = {}
        for docType in self.documents.keys():
            for docSeries in self.documents[docType].keys():
                docRoot = self.documents[docType][docSeries]
                docsWeight[docSeries] = docRoot.treeWeight()
        return docsWeight

    def docSeriesSize(self):
        docsSize = {}
        for docType in self.documents.keys():
            for docSeries in self.documents[docType].keys():
                docRoot = self.documents[docType][docSeries]
                docsSize[docSeries] = docRoot.treeSize()
        return docsSize

    def deleteEmptySeries(self):
        emptySeries = {}
        for docType in self.documents.keys():
            emptySeries[docType] = []
            for docSeries in self.documents[docType].keys():
                if self.documents[docType][docSeries] == None:
                    emptySeries[docType].append(docSeries)
        for docType in emptySeries.keys():
            for docSeries in emptySeries[docType]:
                del self.documents[docType][docSeries]

class KnowledgeDomain():
    def __init__(self, domain, documents, clauseIndex):
        self.domain = domain
        self.docTree = DocTree(documents)
        if Clause.clauseIndex == None:
            Clause.clauseIndex = clauseIndex
        self.llm = LLM(model='llama3.1')
        self.vectorstore = VectorStore(domain=self.domain)
        self.embedding_engine = EmbeddingEngine(model='mxbai-embed-large')
        self.clausestore = ClauseStore(domain=self.domain)
        self.clauseingestor = ClauseIngestor(llm=self.llm, vectorstore=self.vectorstore, embedding_engine=self.embedding_engine, clausestore=self.clausestore, domain=self.domain)

    def __str__(self):
        return json.dumps(
                self,
                default=lambda o: o.__dict__,
                sort_keys=True,
                indent=4)

    def ingestClause(self, clause):
        self.clauseingestor.ingest_clause(clause)

    def addClause(self, clause, rootID):
        parentID = clause.parentID()
        clause.domain = self.domain
        if parentID != None:
            if parentID in Clause.clauseIndex.keys():
                parentClause = Clause.clauseIndex[parentID]
                parentClause.addSubClauseRef(clause.id())
            else:
                logger.warning(f'parent clause not present {parentID}')
        else:
            self.docTree.addRootClause(self.domain, clause, rootID)

    def seriesWeight(self,docSeries):
        for doc in self.docTree.listDocsInTree():
            if doc in Clause.clauseIndex:
                clause = Clause.clauseIndex[doc]
            else:
                short = doc.replace(" ", "")
                clause = Clause.clauseIndex[short]
            if clause.structure.docSeries == docSeries:
                return clause.treeWeight()
        return 0

    def seriesSize(self,docSeries):
        for doc in self.docTree.listDocsInTree():
            if doc in Clause.clauseIndex:
                clause = Clause.clauseIndex[doc]
            else:
                short = doc.replace(" ", "")
                clause = Clause.clauseIndex[short]
            if clause.structure.docSeries == docSeries:
                return clause.treeSize()
        return 0

    def ingestDomainClauses(self):
        for doc in self.docTree.listDocsInTree():
            if doc in Clause.clauseIndex:
                clause = Clause.clauseIndex[doc]
            else:
                short = doc.replace(" ", "")
                clause = Clause.clauseIndex[short]
            clause.ingest(self.clauseingestor)

    def dumpKnowledgeHeadings(self):
        for doc in self.docTree.listDocsInTree():
            if doc in Clause.clauseIndex:
                clause = Clause.clauseIndex[doc]
            else:
                short = doc.replace(" ", "")
                clause = Clause.clauseIndex[short]
            clause.dumpHeadingData()

    def dumpKnowledgeTexts(self):
        for doc in self.docTree.listDocsInTree():
            if doc in Clause.clauseIndex:
                clause = Clause.clauseIndex[doc]
            else:
                short = doc.replace(" ", "")
                clause = Clause.clauseIndex[short]
            clause.dumpTextData()

    def printKnowledgeTexts(self):
        for doc in self.docTree.listDocsInTree():
            if doc in Clause.clauseIndex:
                clause = Clause.clauseIndex[doc]
            else:
                short = doc.replace(" ", "")
                clause = Clause.clauseIndex[short]
            clause.printText()
