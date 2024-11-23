
import numpy as np
from IntelliDoc.ClauseRetriever import ClauseRetriever


class Relationship:
    def __init__(self, clause, parent, retriever):
        self.clause = clause
        self.parent = parent
        self.retriever = retriever
        self.relationships = {}


    def relate(self):
        domain = self.retriever.domain
        if domain not in self.relationships:
            self.relationships[domain]={}
        sentences = self.clause.getSentences()
        if len(sentences)==0:
            return
        scores = []
        averages = []
        maxT = 0
        maxA = 0
        cumulative = {}
        leveled = {}

        for sentence in sentences:
            nodes = self.retriever.retrieve(sentence,10,0)
            for node in nodes:
                score = node.score
                clauseID = node.document.doc_metadata['clause']
                if clauseID in self.relationships[domain]:
                    self.relationships[domain][clauseID]['score'] += score
                    self.relationships[domain][clauseID]['hits'] += 1
                else:
                    self.relationships[domain][clauseID] = {}
                    self.relationships[domain][clauseID]['score'] = score
                    self.relationships[domain][clauseID]['hits'] = 1
        for clauseID in self.relationships[domain]:
            score = self.relationships[domain][clauseID]['score']
            avgScore = score / self.relationships[domain][clauseID]['hits']
            scores.append(score)
            averages.append(avgScore)
            cumulative[clauseID]=score
            leveled[clauseID]=avgScore

        sorted_c = dict(sorted(cumulative.items(), key=lambda x:x[1], reverse=True))
        sorted_l = dict(sorted(leveled.items(), key=lambda x:x[1], reverse=True))
        lsent = len(sentences)
        lcum = len(cumulative)
        spread = lcum/lsent
        c_mean = np.mean(scores)
        c_std = np.std(scores)
        print(f"{self.clause.structure.ID}: {lsent} sentences, {lcum} hits, spread {spread}, c_mean {c_mean} c_std {c_std}")
        bestCum = list(sorted_c.keys())[0]
        bestLev = list(sorted_l.keys())[0]
        nextCum = list(sorted_c.keys())[1]
        nextLev = list(sorted_l.keys())[1]
        print(f"    {bestCum} {cumulative[bestCum]}")
        print(f"    {nextCum} {cumulative[nextCum]}")
        print(f"    {bestLev} {leveled[bestLev]}")
        print(f"    {nextLev} {leveled[nextLev]}")
        clauseID = self.clause.structure.ID
        series=self.clause.structure.docSeries
        if domain == self.clause.domain:
            if bestCum == clauseID:
                if series in ClauseRetriever.hits:
                    ClauseRetriever.hits[series] += 1
                else:
                    ClauseRetriever.hits[series] = 1
            else:
                if series in ClauseRetriever.misses:
                    ClauseRetriever.misses[series] += 1
                else:
                    ClauseRetriever.misses[series] = 1
            if bestLev == clauseID:
                if series in ClauseRetriever.avg_hits:
                    ClauseRetriever.avg_hits[series] += 1
                else:
                    ClauseRetriever.avg_hits[series] = 1
            else:
                if series in ClauseRetriever.avg_misses:
                    ClauseRetriever.avg_misses[series] += 1
                else:
                    ClauseRetriever.avg_misses[series] = 1
            c_accuracy = 0
            l_accuracy = 0
            if series in ClauseRetriever.hits and series in ClauseRetriever.misses:
                c_accuracy = ClauseRetriever.hits[series]/(ClauseRetriever.hits[series]+ClauseRetriever.misses[series])
                l_accuracy = ClauseRetriever.avg_hits[series]/(ClauseRetriever.avg_hits[series]+ClauseRetriever.avg_misses[series])
            print(f"self identification accuracy {c_accuracy} {l_accuracy}")



    def levelUp(self):
        return
