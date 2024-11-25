
import numpy as np
from IntelliDoc.ClauseRetriever import ClauseRetriever


class Relationship:
    def __init__(self, clause, parent, retriever):
        self.clause = clause
        self.parent = parent
        self.retriever = retriever
        self.relationships = {}
        self.s_significance = []
        self.significance = 1


    def relate(self):
        domain = self.retriever.domain
        if domain not in self.relationships:
            self.relationships[domain]={}
        sentences = self.clause.getSentences()
        if len(sentences)==0:
            return
        averages = []
        maxT = 0
        maxA = 0
        cumulative = {}

        s_nr=0
        for sentence in sentences:
            nodes = self.retriever.retrieve(sentence,10,0)
            results={}
            s_max=0
            s_min=1
            s_sum=0
            for node in nodes:
                s_score = node.score
                clauseID = node.document.doc_metadata['clause']
                if clauseID in results:
                    s_sum -= results[clauseID]
                    if results[clauseID] > s_score:
                        s_score = results[clauseID]
                results[clauseID]=s_score
                s_sum += s_score
                if s_max < s_score:
                    s_max = s_score
                if s_min > s_score:
                    s_min = s_score
            nr_res = len(results)
            if nr_res==0:
                print(f"no relationship for {sentence}")
                self.s_significance.append(0) 
                continue
            s_avg = s_sum/nr_res
            s_sig = s_max-s_avg
            sorted_r = dict(sorted(results.items(), key=lambda x:x[1], reverse=True))
            if domain == self.clause.domain:
                s_scatter=0
                for clauseID in sorted_r:
                    score = sorted_r[clauseID]
                    if score < s_avg:
                        continue
                    s_scatter +=1
                if s_scatter == 0:
                    print(f"{self.clause.structure.ID}: no significance for\n{sentence}\n   with {nr_res} results, avg {s_avg}, sig {s_sig}")
                    for clauseID in sorted_r:
                        score = sorted_r[clauseID]
                        print(f"        {clauseID} {score}<{s_avg} {s_sig}")
                    self.s_significance.append(0) 
                else:
                    self.s_significance.append(1/s_scatter) 
            for clauseID in sorted_r:
                score = sorted_r[clauseID]
                if score < s_avg:
                    # print(f"{clauseID} score {score} below avg {s_avg}")
                    continue
                if clauseID in self.relationships[domain]:
                    self.relationships[domain][clauseID]['score'] += score*self.s_significance[s_nr]
                    # self.relationships[domain][clauseID]['score'] += score
                    self.relationships[domain][clauseID]['hits'] += 1
                else:
                    self.relationships[domain][clauseID] = {}
                    self.relationships[domain][clauseID]['score'] = score*self.s_significance[s_nr]
                    # self.relationships[domain][clauseID]['score'] = score
                    self.relationships[domain][clauseID]['hits'] = 1
            s_nr+=1
        c_max=0
        c_min=1
        c_sum=0
        for clauseID in self.relationships[domain]:
            score = self.relationships[domain][clauseID]['score']
            avgScore = score / self.relationships[domain][clauseID]['hits']
            averages.append(avgScore)
            cumulative[clauseID]=score
            c_sum += score
            if c_max < score:
                c_max = score
            if c_min > score:
                c_min = score

        sorted_c = dict(sorted(cumulative.items(), key=lambda x:x[1], reverse=True))
        lsent = len(sentences)
        lcum = len(cumulative)
        scatter = lcum/lsent
        c_avg = c_sum/lcum
        c_sig = c_max-c_avg
        key_list = list(sorted_c.keys())
        print(f"{self.clause.structure.ID}: {lsent} sentences, {lcum} hits, scatter {scatter}, c_avg {c_avg} c_sig {c_sig}")
        if len(key_list) == 0:
            print(f"shit: no keys in sorted_c")
            return
        bestCum = key_list[0]
        if len(key_list)>1:
            nextCum = key_list[1] 
        else:
            nextCum=bestCum
        print(f"    {bestCum} {cumulative[bestCum]}")
        print(f"    {nextCum} {cumulative[nextCum]}")
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
            c_accuracy = 0
            if series in ClauseRetriever.hits and series in ClauseRetriever.misses:
                c_accuracy = ClauseRetriever.hits[series]/(ClauseRetriever.hits[series]+ClauseRetriever.misses[series])
            print(f"self identification accuracy {c_accuracy}")



    def levelUp(self):
        return
