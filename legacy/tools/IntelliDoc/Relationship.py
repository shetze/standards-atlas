import numpy as np
import math
from IntelliDoc.ClauseRetriever import ClauseRetriever
from IntelliDoc.Summarizer import Summarizer
import logging

logger = logging.getLogger(__name__)


class Relationship:
    clusters = None
    clusterStatus = {}

    # This classmethod is iterating over the list of relationship clusters and
    # prints a markdown formatted table with all the related clauses in that
    # cluster.
    # It then calls the qualifyCluster method to generate a textual comparison
    # of the relationships.
    @classmethod
    def clusterDump(cls, clauseIndex):
        for fromParID, toParID in cls.clusters.keys():
            relation = (fromParID, toParID)
            reverse = (toParID, fromParID)
            if reverse in cls.clusters:
                bijective = "Bijective "
            else:
                bijective = ""
                continue
            summarizationItems = {}
            fromPar = clauseIndex[fromParID]
            summarizationItems[fromPar.domain] = []
            summarizationItems[fromPar.domain].append(fromParID)
            fromHeading = fromPar.heading.getBestHeading()
            toPar = clauseIndex[toParID]
            toHeading = toPar.heading.getBestHeading()
            summarizationItems[toPar.domain] = []
            summarizationItems[toPar.domain].append(toParID)
            print(f"\n## {bijective}Relationship Cluster between {fromParID} {fromHeading} and {toParID} {toHeading}\n")
            print("|Clause|Score|RevScore|Peer|")
            print("|---|---|---|---|")
            for memberID in cls.clusters[relation]:
                member = clauseIndex[memberID]
                mHeading = member.heading.getBestHeading()
                for peerID in member.relationship.peers[toPar.domain]:
                    pP = peerID.rsplit(".", 1)[0]
                    if toParID == pP:
                        score = member.relationship.peers[toPar.domain][peerID]['score']
                        revscore = 0
                        peer = clauseIndex[peerID]
                        pHeading = peer.heading.getBestHeading()
                        if reverse in cls.clusters:
                            if peer.relationship != None and memberID in peer.relationship.peers[member.domain]:
                                revscore = peer.relationship.peers[member.domain][memberID]['score']
                        print(f"|{memberID} {mHeading}|{score}|{revscore}|{peerID} {pHeading}|")
                        summarizationItems[fromPar.domain].append(memberID)
                        summarizationItems[toPar.domain].append(peerID)
            print("\n")
            cls.qualifyCluster(clauseIndex,summarizationItems)

    @classmethod
    def qualifyCluster(cls, clauseIndex, summarizationItems):
        # model = "hf.co/ibm-granite/granite-8b-code-instruct-4k-GGUF:latest"
        model = "granite3-moe:latest"
        # model = "nemotron"
        # model = "llama3.1"
        verbose = False
        qualifyer = Summarizer(model)
        D = []
        d = []
        if 'automotive' in summarizationItems:
            D.append('automotive')
            d.append('automotive')
            if 'industry' in summarizationItems:
                D.append('industry')
                d.append('mining industry')
            else:
                D.append('railway')
                d.append('railway')
        else:
            D.append('industry')
            d.append('mining industry')
            D.append('railway')
            d.append('railway')

        clusterPair = (summarizationItems[D[0]][0], summarizationItems[D[1]][0])
        if clusterPair in Relationship.clusterStatus:
            return
        else:
            Relationship.clusterStatus[clusterPair] = 'qualified'

        prompt = f"You are an expert in functional safety. I want to transfer an electronic control unit with a safety application developed for an autonomous vehicle for the {d[0]} safety domain  in compliance with {summarizationItems[D[0]][0]} to the {d[1]} safety domain where we need to to comply with {summarizationItems[D[1]][0]}. The context is providing clauses from the two domains."
        question = "What do the two functional safety domains have in common?\nHow do the two funktional safety domains differ?"
        context = []
        for idx in (0,1):
            parentID = summarizationItems[D[idx]][0]
            parentClause = clauseIndex[parentID]
            pContext = "->".join(parentClause.getContext())
            pType = parentClause.clauseType()
            print(f"## Cluster {D[idx]} {pType} {parentID} {pContext}\n")
            context.append(f"// Start of Context with clauses from the {d[idx]} safety domain {parentID} with headings {pContext}")
            itemList = list(set(summarizationItems[D[idx]]))
            for clauseID in itemList:
                clause = clauseIndex[clauseID]
                context.append("## " + clause.heading.getBestHeading())
                context.append("\n".join(clause.text))
            context.append(f"// End of Context with clauses from the {d[idx]} safety domain")

        text = "\n".join(context)
        # print(text)
        result = qualifyer.request(prompt, question, text.strip(), verbose)
        print("\n".join(result))


    def __init__(self, clause, parent, retriever):
        domain = retriever.domain
        self.clause = clause
        self.parent = parent
        self.retrievers = {}
        self.peers = {}
        self.clusterScore = {}
        self.s_significance = []
        self.significance = 1
        self.lup_support = {}
        self.retrievers[domain] = retriever
        self.relation_file = "relations.csv"

    def addRetriever(self, retriever):
        domain = retriever.domain
        if domain not in self.retrievers:
            self.retrievers[domain] = retriever

    # memorizePeer initializes the relationship dictionary with data loaded
    # from the relation_file
    def memorizePeer(self, peer, score):
        domain = peer.domain
        if domain not in self.peers:
            self.peers[domain] = {}
        peerID = peer.structure.ID
        if not peerID in self.peers[domain]:
            self.peers[domain][peerID] = {}
        self.peers[domain][peerID]["score"] = score
        self.peers[domain][peerID]["status"] = "memorized"

    def relate(self, domain):
        # relate goes through the clause text sentence by sentence, relates
        # them to the given domain and saves the best matching relationships in
        # the relation_file for further use.

        # no duplicates
        if self.clause.relStat[domain] == "matched":
            return
        # we skip all clauses that have failed the Level 1 KPI of self-identiy matching
        if self.clause.selfaware < 1:
            return

        if domain not in self.peers:
            self.peers[domain] = {}
        sentences = self.clause.getTokens()
        if len(sentences) == 0:
            return
        self._process_sentences(domain, sentences)
        related = self.best_matches_for_domain(domain, 3)
        if domain == self.clause.domain:
            return
        try:
            with open(self.relation_file, "a") as store:
                for relClause in related:
                    score = self.peers[domain][relClause]["score"]
                    store.write(f"{self.clause.structure.ID};{relClause};{score}\n")
                store.close
        except IOError as e:
            logger.warning(f"file open error: {e}")

    # _process_sentences does the actual work of finding relating clauses in
    # the given domain based on the list of sentences.
    def _process_sentences(self, domain, sentences):
        scatter = []
        signife = []
        for enum_i, sentence in enumerate(sentences):
            if domain in self.retrievers:
                nodes = self.retrievers[domain].retrieve(sentence, 10, 0)
            else:
                clauseID = self.clause.structure.ID
                print(f"Oops: Domain {domain} is missing for {clauseID}")
                return
            results = {}
            s_max = 0
            s_min = 1
            s_sum = 0
            # for each sentence in one clause, we iterate over the set of nodes identified by the retriever
            # as semantically close matches in the vector store.

            for node in nodes:
                s_score = node.score
                clauseID = node.document.doc_metadata["clause"]
                clauseType = node.document.doc_metadata["type"]
                # upvoting of clauses from the same type
                if clauseType == self.clause.clauseType():
                    print(f"{clauseID} type matches {clauseType} score {s_score}")
                    s_score = s_score * 2
                # the result set from the retriever may contain more than one node referring to the same clause.
                # only the higest score is used
                if clauseID in results:
                    s_sum -= results[clauseID]
                    # t1 = math.tan(results[clauseID]*math.pi/2)
                    # t2 = math.tan(s_score*math.pi/2)
                    # s_score = math.atan(t1+t2)*2/math.pi
                    if results[clauseID] > s_score:
                        s_score = results[clauseID]
                results[clauseID] = s_score

                # One result of the following block is to evaluate each sentence
                # in the clause regarding its significance s_sig. The null hypothesis
                # for the significance is that all sentences of a clause recognize
                # self-identity with the same score in the semantic comparison.
                s_sum += s_score
                if s_max < s_score:
                    s_max = s_score
                if s_min > s_score:
                    s_min = s_score
            nr_res = len(results)
            if nr_res == 0:
                print(f"no relationship for {sentence}")
                self.s_significance.append(0)
                continue
            s_avg = s_sum / nr_res
            s_sig = s_max - s_avg
            sorted_r = dict(sorted(results.items(), key=lambda x: x[1], reverse=True))

            # We are in the context of one sentence of the clause and have the
            # dictionary with related clauses from the same domain matching
            # that sentence.  We have started with 10 nodes returned from the
            # retriever. If all the 10 nodes refer to one single clause, 
            # the scattering is at its minimum (1).

            # We typically expect more than one matching clause to be found by
            # the retriever, so the result is somewhat scattered.  Each
            # matching node comes with a score between 0 and 1 and we want to
            # take into account only those nodes, that come with at least
            # average score.

            # We store both the significance and the scattering values per
            # sentence as they are found for the self-identity matching. These
            # values are then later on used to weight the results for the cross
            # domain retrieval.
            if domain == self.clause.domain:
                signife.append(s_sig)
                s_scatter = 0
                for clauseID in sorted_r:
                    score = sorted_r[clauseID]
                    if score < s_avg:
                        break
                    s_scatter += 1
                if s_scatter == 0:
                    # this should never happen, so we may remove this if branch entirely
                    print(
                        f"{self.clause.structure.ID}: no scatter for\n{sentence}\n   with {nr_res} results, avg {s_avg}, sig {s_sig}"
                    )
                    for clauseID in sorted_r:
                        score = sorted_r[clauseID]
                        print(f"        {clauseID} {score}<{s_avg} {s_sig}")
                    scatter.append(0)
                else:
                    scatter.append(s_scatter)

            # The following block is unconditonal for each sentence in a
            # clause. We have a sorted dictionary with all clauses that the
            # retriever has referred the sentence to.
            # Now we add all the clauses with at least average scores to the
            # object instance relationship dictionary.
            for clauseID in sorted_r:
                score = sorted_r[clauseID]
                if len(self.clause.sign) < enum_i:
                    print(f"{self.clause.structure.ID}: weight sign mismatch {enum_i}")
                    break
                if score < s_avg:
                    break
                try:
                    if clauseID in self.peers[domain]:
                        # Trigonometric calculation seemingly does not improve the result.
                        # ps = self.peers[domain][clauseID]['score']
                        # t1 = math.tan(ps*math.pi/2)
                        # t2 = math.tan(score*math.pi/2)
                        # score = math.atan(t1+t2)*2/math.pi
                        if self.peers[domain][clauseID]["status"] == "loading":

                            # here we use the significance of each sentence
                            # calculated with regards to the self-identity
                            # matching to weight the scores. 
                            # TODO: what happens if we are in the self-identiy case?
                            #       should we initialize the clause.sign list with 1?
                            self.peers[domain][clauseID]["score"] += (
                                score * self.clause.sign[i]
                            )
                            self.peers[domain][clauseID]["hits"] += 1
                    else:
                        self.peers[domain][clauseID] = {}
                        self.peers[domain][clauseID]["score"] = (
                            score * self.clause.sign[i]
                        )
                        self.peers[domain][clauseID]["hits"] = 1
                        self.peers[domain][clauseID]["status"] = "loading"
                except IndexError as e:
                    len_s = len(self.clause.sign)
                    print(f"{self.clause.structure.ID}: index error {len_s} {enum_i} {e}")
                    self.peers[domain][clauseID] = {}
                    self.peers[domain][clauseID]["score"] = score
                    self.peers[domain][clauseID]["hits"] = 1
                    self.peers[domain][clauseID]["status"] = "loading"

        # All sentences processed.
        # We finally go over the arrays of significance and scattering for all
        # sentences in one clause, normalize them and write them as csv for
        # future use.
        if domain == self.clause.domain:
            len_se = len(sentences)
            len_sc = len(scatter)
            len_si = len(signife)

            if len_se != len_sc or len_se != len_si:
                print(
                    f"{self.clause.structure.ID}: weight array mismatch {len_se} {len_sc} {len_si}"
                )
            scat_mean = np.mean(scatter)
            sign_mean = np.mean(signife)
            scat_list = np.array(scatter) / scat_mean
            sign_list = np.array(signife) / sign_mean
            # print(f"{self.clause.structure.ID}: {len_se} sentences weights\n   {self.clause.scat}\n    {self.clause.sign}")
            try:
                with open("weights.csv", "a") as store:
                    weights = f"{self.clause.structure.ID};{np.array2string(scat_list,separator=',',max_line_width=3000)};{np.array2string(sign_list,separator=',',max_line_width=3000)}\n"
                    store.write(weights)
                    store.close
            except IOError as e:
                logger.warning(f"file open error: {e}")

    # The sentence by sentence retrieval process generates a list of matching clauses each with a summed up score value.
    # The best_matches_for_domain method returns a list of IDs for clauses with the highest score.
    def best_matches_for_domain(self, domain, count=3, verbose=True):
        c_max = 0
        c_sum = 0
        scores = {}
        for clauseID in self.peers[domain]:
            if self.peers[domain][clauseID]["status"] != "loading":
                continue
            score = self.peers[domain][clauseID]["score"]
            self.peers[domain][clauseID]["status"] = "matched"
            scores[clauseID] = score
            c_sum += score
            if c_max < score:
                c_max = score

        sorted_c = dict(sorted(scores.items(), key=lambda x: x[1], reverse=True))
        key_list = list(sorted_c.keys())
        if len(key_list) == 0:
            self.clause.relStat[domain] = "matched"
            return key_list

        # The following block provides some debugging output regarding the
        # quality of the matching process.  In particular, we keep track of the
        # self-identiy matching and calculate the accuracy as the percentage of
        # clauses that have self-identiy as the best match (Level 1 KPI).
        if verbose:
            lcum = len(scores)
            c_avg = c_sum / lcum
            c_sig = c_max - c_avg
            print(f"{self.clause.structure.ID}: {lcum} hits, c_avg {c_avg} c_sig {c_sig}")
            bestClause = key_list[0]
            print(f"    {bestClause} {scores[bestClause]}")
            clauseID = self.clause.structure.ID
            series = self.clause.structure.docSeries
            if domain == self.clause.domain:
                if bestClause == clauseID:
                    if series in ClauseRetriever.hits:
                        ClauseRetriever.hits[series] += 1
                    else:
                        ClauseRetriever.hits[series] = 1
                else:
                    self.clause.selfaware /= 2
                    if series in ClauseRetriever.misses:
                        ClauseRetriever.misses[series] += 1
                    else:
                        ClauseRetriever.misses[series] = 1
                c_accuracy = 1
                if series in ClauseRetriever.hits and series in ClauseRetriever.misses:
                    c_accuracy = ClauseRetriever.hits[series] / (
                        ClauseRetriever.hits[series] + ClauseRetriever.misses[series]
                    )
                print(
                    f"{self.clause.structure.ID}: self identification accuracy {c_accuracy}"
                )

        return key_list[:count]

    # Here we try to take into account the sibling/parent relationships of
    # clauses and calculate the Level 2 KPI.  This needs to be reworked.
    def levelUp(self, domain):
        if len(self.clause.subclauses) == 0:
            return
        lup_rel = {}
        for clauseID in self.clause.subclauses:
            subClause = self.clause.getClauseByID(clauseID)
            if domain not in subClause.relationship.peers:
                print(
                    f"{self.clause.structure.ID}: levelUp domain {domain} not in peers"
                )
                continue
            for refClause in subClause.relationship.peers[domain]:
                lupClause = refClause.rsplit(".", 1)[0]
                score = subClause.relationship.peers[domain][refClause]["score"]
                if lupClause in lup_rel:
                    lup_rel[lupClause] += score
                else:
                    lup_rel[lupClause] = score

        sorted_lr = dict(sorted(lup_rel.items(), key=lambda x: x[1], reverse=True))
        if len(sorted_lr) == 0:
            print(
                f"{self.clause.structure.ID}: levelUp has found no peers for domain {domain}"
            )
            return
        key_list = list(sorted_lr.keys())
        bestLup = key_list[0]
        self.lup_support[domain] = bestLup
        if domain == self.clause.domain:
            series = self.clause.structure.docSeries
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
            if (
                series in ClauseRetriever.lup_hits
                and series in ClauseRetriever.lup_misses
            ):
                accuracy = ClauseRetriever.lup_hits[series] / (
                    ClauseRetriever.lup_hits[series]
                    + ClauseRetriever.lup_misses[series]
                )
            print(
                f"{self.clause.structure.ID} subs identification {bestLup} level accuracy {accuracy}"
            )

        return
