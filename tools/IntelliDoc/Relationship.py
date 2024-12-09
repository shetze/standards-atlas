
import numpy as np
import math
from IntelliDoc.ClauseRetriever import ClauseRetriever
import logging
logger = logging.getLogger(__name__)


class Relationship:
    def __init__(self, clause, parent, retriever):
        domain = retriever.domain
        self.clause = clause
        self.parent = parent
        self.retrievers = {}
        self.relationships = {}
        self.s_significance = []
        self.significance = 1
        self.lup_support = {}
        self.retrievers[domain] = retriever
        self.relation_file = 'relations.csv'

    def addRetriever(self, retriever):
        domain = retriever.domain
        self.retrievers[domain] = retriever

    def relate(self, domain):
        # relate goes through the clause text sentence by sentence and retrieves the
        # 10 best matches for each sentence from the embedded content in a specific
        # domain.
        # The number of sentences in each clause text does vary. 

        # no duplicates, no junk
        if self.clause.relStat[domain] == 'matched':
            return
        if self.clause.distinctness < 1:
            return

        if domain not in self.relationships:
            self.relationships[domain]={}
        sentences = self.clause.getTokens()
        if len(sentences)==0:
            return
        self._process_sentences(domain, sentences)
        related = self.best_match_for_domain(domain)
        if domain == self.clause.domain:
            return
        try:
            with open(self.relation_file, 'a') as store:
                for relClause in related:
                    score = self.relationships[domain][relClause]['score']
                    store.write(f"{self.clause.structure.ID};{relClause};{score}\n")
                store.close
        except IOError as e:
            logger.warning(f"file open error: {e}")

    def _process_sentences(self, domain, sentences):
        scatter = []
        signife = []
        for i, sentence in enumerate(sentences):
            if domain in self.retrievers:
                nodes = self.retrievers[domain].retrieve(sentence,10,0)
            else:
                clauseID = self.clause.structure.ID
                print(f"Oops: Domain {domain} is missing for {clauseID}")
                return
            results={}
            s_max=0
            s_min=1
            s_sum=0
            for node in nodes:
                s_score = node.score
                clauseID = node.document.doc_metadata['clause']
                clauseType = node.document.doc_metadata['type']
                # if clauseType == 'requirement' and clauseType == self.clause.clauseType():
                if clauseType == self.clause.clauseType():
                    print(f"{clauseID} type matches {clauseType} score {s_score}")
                    s_score = s_score*2
                if clauseID in results:
                    s_sum -= results[clauseID]
                    # t1 = math.tan(results[clauseID]*math.pi/2)
                    # t2 = math.tan(s_score*math.pi/2)
                    # s_score = math.atan(t1+t2)*2/math.pi
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

            # the purpose of the following block is to evaluate each sentence in the clause
            # regarding its distinctness. We are in the context of one sentence
            # of the clause and have the dictionary with related clauses matching that sentence.
            # We have started with 10 nodes returned from the retriever. If all the 10 nodes refer
            # to one single clause, we say the distinctness is at its maximum (1).
            # We typically expect more than one matching clause to be found by the retriever,
            # so the result is somewhat scattered.
            # Each matching node comes with a score between 0 and 1 and we want to take into
            # account only those nodes, that come with at least average score.
            # We define the distinctness as the reciprocal of the number of matching clauses
            # with at least average score.
            # We finally store this distinctness value for each sentence as entry in the
            # clause.sentdist array for further use.
            if domain == self.clause.domain:
                signife.append(s_sig)
                s_scatter=0
                for clauseID in sorted_r:
                    score = sorted_r[clauseID]
                    if score < s_avg:
                        break
                    s_scatter +=1
                if s_scatter == 0:
                    # this should never happen, so we may remove this if branch entirely
                    print(f"{self.clause.structure.ID}: no significance for\n{sentence}\n   with {nr_res} results, avg {s_avg}, sig {s_sig}")
                    for clauseID in sorted_r:
                        score = sorted_r[clauseID]
                        print(f"        {clauseID} {score}<{s_avg} {s_sig}")
                    self.clause.sentdist.append(0) 
                    scatter.append(0)
                else:
                    self.clause.sentdist.append(1/s_scatter) 
                    scatter.append(s_scatter)

            # the following block is unconditonal for each sentence in a clause.
            # we have a sorted dictionary with all clauses that the retriever has referred the
            # sentence to.
            # Now we add all the clauses with at least average scores to the object instance relationship
            # dictionary
            # trigonometric calculation seemingly does not improve the result.
            # 

            for clauseID in sorted_r:
                score = sorted_r[clauseID]
                if len(self.clause.sign)<i:
                    print(f"{self.clause.structure.ID}: weight sign mismatch {i}")
                    break
                if score < s_avg:
                    break
                try:
                    if clauseID in self.relationships[domain]:
                        # ps = self.relationships[domain][clauseID]['score']
                        # t1 = math.tan(ps*math.pi/2)
                        # t2 = math.tan(score*math.pi/2)
                        # score = math.atan(t1+t2)*2/math.pi
                        if self.relationships[domain][clauseID]['status'] == 'loading':
                            self.relationships[domain][clauseID]['score'] += score * self.clause.sign[i]
                            self.relationships[domain][clauseID]['hits'] += 1
                    else:
                        self.relationships[domain][clauseID] = {}
                        self.relationships[domain][clauseID]['score'] = score * self.clause.sign[i]
                        self.relationships[domain][clauseID]['hits'] = 1
                        self.relationships[domain][clauseID]['status'] = 'loading'
                except IndexError as e:
                    len_s = len(self.clause.sign)
                    print(f"{self.clause.structure.ID}: index error {len_s} {i} {e}")
                    self.relationships[domain][clauseID] = {}
                    self.relationships[domain][clauseID]['score'] = score
                    self.relationships[domain][clauseID]['hits'] = 1
                    self.relationships[domain][clauseID]['status'] = 'loading'
        # all sentences processed
        if domain == self.clause.domain:
            len_se = len(sentences)
            len_sc = len(scatter)
            len_si = len(signife)

            if len_se != len_sc or len_se != len_si:
                print(f"{self.clause.structure.ID}: weight array mismatch {len_se} {len_sc} {len_si}")
            scat_mean=np.mean(scatter)
            sign_mean=np.mean(signife)
            scat_list=np.array(scatter)/scat_mean
            sign_list=np.array(signife)/sign_mean
            # print(f"{self.clause.structure.ID}: {len_se} sentences weights\n   {self.clause.scat}\n    {self.clause.sign}")
            try:
                with open('weights.csv', 'a') as store:
                    weights=f"{self.clause.structure.ID};{np.array2string(scat_list,separator=',',max_line_width=3000)};{np.array2string(sign_list,separator=',',max_line_width=3000)}\n"
                    store.write(weights)
                    store.close
            except IOError as e:
                logger.warning(f"file open error: {e}")



    def best_match_for_domain(self, domain, count=3):
        c_max=0
        c_min=1
        c_sum=0
        scores = {}
        averages = []
        for clauseID in self.relationships[domain]:
            if self.relationships[domain][clauseID]['status'] != 'loading':
                continue
            score = self.relationships[domain][clauseID]['score']
            avgScore = score / self.relationships[domain][clauseID]['hits']
            self.relationships[domain][clauseID]['status'] = 'matched'
            averages.append(avgScore)
            scores[clauseID]=score
            c_sum += score
            if c_max < score:
                c_max = score
            if c_min > score:
                c_min = score

        sorted_c = dict(sorted(scores.items(), key=lambda x:x[1], reverse=True))
        key_list = list(sorted_c.keys())
        if len(key_list) == 0:
            self.clause.relStat[domain]='matched'
            return key_list
        lcum = len(scores)
        c_avg = c_sum/lcum
        c_sig = c_max-c_avg
        print(f"{self.clause.structure.ID}: {lcum} hits, c_avg {c_avg} c_sig {c_sig}")
        bestClause = key_list[0]
        print(f"    {bestClause} {scores[bestClause]}")
        clauseID = self.clause.structure.ID
        series=self.clause.structure.docSeries
        if domain == self.clause.domain:
            if bestClause == clauseID:
                if series in ClauseRetriever.hits:
                    ClauseRetriever.hits[series] += 1
                else:
                    ClauseRetriever.hits[series] = 1
            else:
                self.clause.distinctness /= 2
                if series in ClauseRetriever.misses:
                    ClauseRetriever.misses[series] += 1
                else:
                    ClauseRetriever.misses[series] = 1
            c_accuracy = 1
            if series in ClauseRetriever.hits and series in ClauseRetriever.misses:
                c_accuracy = ClauseRetriever.hits[series]/(ClauseRetriever.hits[series]+ClauseRetriever.misses[series])
            print(f"{self.clause.structure.ID}: self identification accuracy {c_accuracy}")
        return key_list[:count]


    def levelUp(self, domain):
        if len(self.clause.subclauses)==0:
            return
        lup_rel={}
        for clauseID in self.clause.subclauses:
            subClause = self.clause.getClauseByID(clauseID)
            if domain not in subClause.relationship.relationships:
                print(f"{self.clause.structure.ID}: levelUp domain {domain} not in relationships")
                continue
            for refClause in subClause.relationship.relationships[domain]:
                lupClause = refClause.rsplit(".",1)[0]
                score = subClause.relationship.relationships[domain][refClause]['score']
                if lupClause in lup_rel:
                    lup_rel[lupClause] += score
                else:
                    lup_rel[lupClause] = score

        sorted_lr = dict(sorted(lup_rel.items(), key=lambda x:x[1], reverse=True))
        if len(sorted_lr) == 0:
            print(f"{self.clause.structure.ID}: levelUp has found no relationships for domain {domain}")
            return
        key_list = list(sorted_lr.keys())
        bestLup = key_list[0]
        self.lup_support[domain]=bestLup
        if domain == self.clause.domain:
            series=self.clause.structure.docSeries
            if bestLup == self.clause.structure.ID:
                if series in ClauseRetriever.lup_hits:
                    ClauseRetriever.lup_hits[series] += 1
                else:
                    ClauseRetriever.lup_hits[series] = 1
            else:
                if series in ClauseRetriever.lup_misses:
                    ClauseRetriever.lup_misses[series] += 1
                else:
                    ClauseRetriever.lup_misses[series] = 1
            accuracy = 1
            if series in ClauseRetriever.lup_hits and series in ClauseRetriever.lup_misses:
                accuracy = ClauseRetriever.lup_hits[series]/(ClauseRetriever.lup_hits[series]+ClauseRetriever.lup_misses[series])
            print(f"{self.clause.structure.ID} subs identification {bestLup} level accuracy {accuracy}")

        return
