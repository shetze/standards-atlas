import re
import logging
import ollama
import json
from natsort import natsorted
from IntelliDoc.Clause import Clause, ClauseID, ClauseHeading

logger = logging.getLogger(__name__)


class HeadingFactory:
    hl_pattern = {
        "llama3.1": r'^[^"]*"(.+)"\W?$',
        "nemotron": r"^[1-9]\.\s+\*+([\w\s.&-/]+)\*+",
        "granite3-moe": r'^[^"]*"(.+)"\W?$',
        "granite3-dense": r'^[^"]*"(.+)"\W?$',
        "hf.co/ibm-granite/granite-8b-code-instruct-4k-GGUF": r'^[^"]*"(.+)"\W?$',
    }

    def __init__(self, model):
        self.headingWords = 3
        if model in HeadingFactory.hl_pattern:
            self.model = model
        else:
            self.model = "nemotron"
        self.hl_regex = re.compile(HeadingFactory.hl_pattern[self.model])

    def generate_headings(self, clause, verbose=False):
        headings = []
        clauseType = clause.clauseType()
        text = clause.getText()
        if len(text) == 0:
            return headings
        prompt = f"create a max {self.headingWords} word headline for the following {clauseType}: {text}"
        attempt = 0
        while len(headings) == 0:
            response = ollama.generate(model=self.model, prompt=prompt)
            for line in response["response"].splitlines():
                match = self.hl_regex.match(line)
                if match:
                    headings.append(match[1])
            attempt += 1
            if verbose:
                print(
                    f"\n\ngenerate headings for {clause.structure.ID} attempt {attempt}\n{prompt}\n\n"
                )
                print(response["response"])
            if attempt > 5:
                logger.warning(
                    f"no heading offer from {self.model} for {text} in {response['response']}"
                )
                return headings
        return headings

    def generate_alternative_headings(
        self, clause, cacheFile=None, force=False, verbose=False
    ):
        if clause.heading.isSpecific() and not force:
            return
        alternatives = self.generate_headings(clause, verbose)
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

    def headings4all(self, cacheFile=None, force=False, verbose=False):
        for clauseID in Clause.clauseIndex:
            clause = Clause.clauseIndex[clauseID]
            if clause.heading.isSpecific() and not force:
                continue
            self.generate_alternative_headings(clause, cacheFile, force, verbose)

    def load_alternatives_from_file(self, cacheFile):
        try:
            with open(cacheFile, "r") as store:
                for line in store:
                    if re.match("^#", line):
                        clauseID = line[2:].rstrip()
                    else:
                        match = self.hl_regex.match(line)
                        if match:
                            if clauseID not in Clause.clauseIndex:
                                continue
                            clause = Clause.clauseIndex[clauseID]
                            display = clause.heading.display
                            clause.heading.addAlternative(
                                match[1], "generated", self.model
                            )
        except IOError as e:
            logger.warning(f"file open error: {e}")
