import re
import logging
import ollama
import json
from natsort import natsorted

logger = logging.getLogger(__name__)


class Summarizer:
    skip_pattern = {
        "llama3.1": r".*summary.*",
        "nemotron": r"^[1-9]\.\s+\*+([\w\s.&-/]+)\*+",
        "granite3-moe": r'^[^"]*"(.+)"\W?$',
        "granite3-dense": r'^[^"]*"(.+)"\W?$',
        "hf.co/ibm-granite/granite-8b-code-instruct-4k-GGUF": r'^[^"]*"(.+)"\W?$',
    }

    def __init__(self, model):
        if model in Summarizer.skip_pattern:
            self.model = model
        else:
            self.model = "nemotron"
        self.skip_regex = re.compile(Summarizer.skip_pattern[self.model], re.IGNORECASE)
        self.sumstore = {}

    def request(self, prompt, question, text, verbose=False):
        reply = []
        if len(text) == 0:
            return reply
        attempt = 0
        request = f"System: {prompt}:\n\nContext: {text}\n\nQuestion: {question}"
        while len(reply) == 0:
            response = ollama.generate(model=self.model, prompt=request)
            for line in response["response"].splitlines():
                match = self.skip_regex.match(line, re.IGNORECASE)
                if match:
                    continue
                reply.append(line)
            while len(reply) > 0 and reply[0] == "":
                reply.pop(0)
            while len(reply) > 0 and reply[-1] == "":
                reply.pop(-1)

            attempt += 1
            if verbose:
                print(
                    f"\n\n---------------------------------------------\ngenerate reply for request attempt {attempt}\n{prompt}\n\n--------------------------------------------"
                )
                print("\n".join(reply))
            if attempt > 5:
                logger.warning(
                    f"no reply offer from {self.model} for {text} in {response['response']}"
                )
                return reply
        return reply

    def summarize(self, clause, text, verbose=False):
        summary = []
        clauseType = clause.clauseType()
        clauseID = clause.structure.ID
        if len(text) == 0:
            return summary
        prompt = f"create a plain summary for the following {clauseType}. Do not add any introduction, question or comments: {text}"
        attempt = 0
        while len(summary) == 0:
            response = ollama.generate(model=self.model, prompt=prompt)
            for line in response["response"].splitlines():
                match = self.skip_regex.match(line, re.IGNORECASE)
                if match:
                    continue
                summary.append(line)
            while len(summary) > 0 and summary[0] == "":
                summary.pop(0)
            while len(summary) > 0 and summary[-1] == "":
                summary.pop(-1)

            attempt += 1
            if verbose:
                print(
                    f"\n\n---------------------------------------------\ngenerate summary for {clause.structure.ID} attempt {attempt}\n{prompt}\n\n--------------------------------------------"
                )
                print("\n".join(summary))
            if attempt > 5:
                logger.warning(
                    f"no summary offer from {self.model} for {text} in {response['response']}"
                )
                return summary
        self.sumstore[clauseID] = summary
        return summary

    def generate_summaries(self, clause, cacheFile=None, force=False, verbose=False):
        if clause.isSummarized() and not force:
            return
        summary = self.summarize(clause, verbose)
        for i in range(len(alternatives)):
            clause.heading.addAlternative(alternatives[i], "generated", self.model)
        if cacheFile != None:
            try:
                with open(cacheFile, "a") as store:
                    store.write(f"# {clause.structure.ID}\n")
                    for i in range(len(alternatives)):
                        store.write(alternatives[i] + "\n")
                    store.write("\n\n")
                store.close()
            except IOError as e:
                logger.warning(f"file open error: {e}")

    def summaries4all(self, clauseIndex, cacheFile=None, force=False, verbose=False):
        for clauseID in clauseIndex:
            clause = clauseIndex[clauseID]
            if clause.isSummarized() and not force:
                continue
            self.generate_summaries(clause, cacheFile, force, verbose)

    def dump_sumstore(self, cacheFile="sumstore.json"):
        try:
            with open(cacheFile, "a") as store:
                store.write(
                    json.dumps(
                        self.sumstore,
                        default=lambda o: o.__dict__,
                        sort_keys=True,
                        indent=4,
                    )
                )
                store.close()
        except IOError as e:
            logger.warning(f"file open error: {e}")

    def load_summaries_from_file(self, clauseIndex, cacheFile):
        try:
            with open(cacheFile, "r") as store:
                for line in store:
                    if re.match("^#", line):
                        clauseID = line[2:].rstrip()
                        clause = clauseIndex[clauseID]
                    else:
                        clause.summary.append(line)
        except IOError as e:
            logger.warning(f"file open error: {e}")
