import re
import logging
import hashlib
import nltk
from IntelliDoc.Relationship import Relationship
from llama_index.core.node_parser.text.utils import split_by_sentence_tokenizer_internal

logger = logging.getLogger(__name__)

alphabets= "([A-Za-z])"
prefixes = "(Mr|St|Mrs|Ms|Dr)[.]"
suffixes = "(Inc|Ltd|Jr|Sr|Co)"
starters = "(Mr|Mrs|Ms|Dr|Prof|Capt|Cpt|Lt|He\s|She\s|It\s|They\s|Their\s|Our\s|We\s|But\s|However\s|That\s|This\s|Wherever)"
acronyms = "([A-Z][.][A-Z][.](?:[A-Z][.])?)"
websites = "[.](com|net|org|io|gov|edu|me)"
digits = "([0-9])"
multiple_dots = r'\.{2,}'

def split_into_sentences(text):
    """
    Split the text into sentences.

    If the text contains substrings "<prd>" or "<stop>", they would lead
    to incorrect splitting because they are used as markers for splitting.

    :param text: text to be split into sentences
    :type text: str

    :return: list of sentences
    :rtype: list[str]
    """
    text = " " + text + "  "
    text = text.replace("\n"," ")
    text = re.sub(prefixes,"\\1<prd>",text)
    text = re.sub(websites,"<prd>\\1",text)
    text = re.sub(digits + "[.]" + digits,"\\1<prd>\\2",text)
    text = re.sub(multiple_dots, lambda match: "<prd>" * len(match.group(0)) + "<stop>", text)
    if "Ph.D" in text: text = text.replace("Ph.D.","Ph<prd>D<prd>")
    text = re.sub("\s" + alphabets + "[.] "," \\1<prd> ",text)
    text = re.sub(acronyms+" "+starters,"\\1<stop> \\2",text)
    text = re.sub(alphabets + "[.]" + alphabets + "[.]" + alphabets + "[.]","\\1<prd>\\2<prd>\\3<prd>",text)
    text = re.sub(alphabets + "[.]" + alphabets + "[.]","\\1<prd>\\2<prd>",text)
    text = re.sub(" "+suffixes+"[.] "+starters," \\1<stop> \\2",text)
    text = re.sub(" "+suffixes+"[.]"," \\1<prd>",text)
    text = re.sub(" " + alphabets + "[.]"," \\1<prd>",text)
    if "”" in text: text = text.replace(".”","”.")
    if "\"" in text: text = text.replace(".\"","\".")
    if "!" in text: text = text.replace("!\"","\"!")
    if "?" in text: text = text.replace("?\"","\"?")
    text = text.replace(".",".<stop>")
    text = text.replace("?","?<stop>")
    text = text.replace("!","!<stop>")
    text = text.replace("<prd>",".")
    sentences = text.split("<stop>")
    sentences = [s.strip() for s in sentences]
    if sentences and not sentences[-1]: sentences = sentences[:-1]
    return sentences

class ClauseHeading():
    def __init__(self, displayHeading):
        self.display = displayHeading
        self.alternatives = {}
        self.state = 'loaded'

    def addAlternative(self, heading, status, source):
        if heading in self.alternatives.keys():
            return
        self.alternatives[heading]={}
        self.alternatives[heading]['status'] = status
        self.alternatives[heading]['source'] = source
        if status == 'parsed' and self.display in ( 'TOC', 'REQUIREMENT', 'OBJECTIVE', 'SCOPE', 'TERM' ):
            self.display = heading
            self.state = 'parsed'

    def isSpecific(self):
        if self.display == '':
            return False
        if self.display in ( 'TOC', 'REQUIREMENT', 'OBJECTIVE', 'SCOPE', 'TERM' ) and self.alternatives == {}:
            return False
        else:
            return True

    def getBestHeading(self):
        heading = self.display
        if heading in ( 'TOC', 'REQUIREMENT', 'OBJECTIVE', 'SCOPE', 'TERM' ):
            for alternative in self.alternatives.keys():
                if self.alternatives[alternative]['status'] == 'selected':
                    heading = alternative
                    self.state = 'best selected'
                    break
                if self.alternatives[alternative]['status'] == 'generated':
                    heading = alternative
                    self.state = 'best generated'
        return heading

    def __str__(self):
        return "{0} {1}".format(self.display, self.alternatives)

class ClauseID():
    clauseRegex = {}
    def __init__(self, clauseID, docType):
        clausePatterns = {
                'standard' : r'([A-Z\s]+\s+\d\d\d\d\d?)-?(\d*):\d\d\d\d\s+([1-9A-Z]+[0-9.]*)',
                'generic' : r'(\w+)-?(\d*)-([1-9A-Z]+[0-9.]*)'
                }
        self.ID = clauseID
        self.doorstopID = None

        if not docType in clausePatterns.keys():
            logger.error(f"clauseID {clauseID} docType not supported: {docType}\n\tfalling back to generic")
            docType = generic
        self.docType = docType

        if not docType in ClauseID.clauseRegex.keys():
            regex = re.compile(clausePatterns[docType])
            ClauseID.clauseRegex[docType] = regex

        match = ClauseID.clauseRegex[docType].match(self.ID)
        if match:
            self.docSeries = match[1].replace(" ", "")
            self.seriesPart = match[2]
            self.chapter = match[3]
            self.level = self.chapter.count('.')+1
        else:
            logger.warning(f"no match for clauseID {clauseID} docType {docType}")
            self.docSeries = self.ID
            self.seriesPart = ''
            self.chapter = '0.0'
            self.level = 0

    def docSeries(self):
        return self.docSeries.replace(" ", "")

    def multipartSeries(self):
        if self.seriesPart == '':
            return False
        else:
            return True

    def parentID(self):
        if self.level > 1:
            return self.ID.rpartition('.')[0]
        else:
            return None


    def __str__(self):
        return "{0} {1} {2}".format(self.ID, self.docSeries, self.chapter)

class Clause():
    clauseIndex = None
    relations = None
    def __init__(self, clauseID, clauseHeading = 'Clause', clauseType = 'c', docType = 'standard', domain = 'generic'):
        self.structure = ClauseID(clauseID, docType)
        self.type = clauseType
        self.heading = ClauseHeading(clauseHeading)
        self.domain = domain
        self.relSelf = False
        self.keywords = []
        self.subclauses = []
        self.text = []
        self.sentences = []
        self.summary = []
        self.relationship = None
        self.distinctness = 1
        self.sentdist = []
        self.relStat = { 'industry':'new', 'railway':'new', 'automotive':'new' }
        self.scat = []
        self.sign = []

    def __str__(self):
        heading = '#' * self.structure.level
        heading += ' '
        heading += self.structure.ID
        heading += ' '
        heading += self.heading.getBestHeading()
        body = '\n'.join(self.text)
        return f"{heading}\n\n{body.strip()}"

    def clauseType(self):
        typedict = {
                'a' : 'abbreviation',
                'c' : 'clause',
                'm' : 'technique / measure',
                'o' : 'objective',
                'r' : 'requirement',
                's' : 'scope',
                't' : 'term',
                'u' : 'text',
                'x' : 'root',
                }
        return typedict[self.type]

    def id(self):
        return self.structure.ID

    def getClauseByID(self, clauseID, force=False):
        if clauseID not in Clause.clauseIndex:
            if force:
                clause = Clause(clauseID)
                Clause.clauseIndex[clauseID] = clause
            else:
                return None
        return Clause.clauseIndex[clauseID]

    def docType(self):
        return self.structure.docType

    def seriesPart(self):
        return self.structure.seriesPart

    def multipartSeries(self):
        return self.structure.multipartSeries()

    def docSeries(self):
        return self.structure.docSeries

    def addText(self, line):
        self.text.append(line)

    def getSentences(self):
        text = ' '.join(self.text)
        return split_into_sentences(text)

    def getText(self):
        text = ' '.join(self.text)
        return text.strip()

    def getTokens(self):
        text = ' '.join(self.text)
        tokenizer = nltk.tokenize.PunktSentenceTokenizer()
        return split_by_sentence_tokenizer_internal(text.strip(), tokenizer)

    def parentID(self):
        return self.structure.parentID()

    def hasSubClauseRef(self, clauseID):
        if clauseID in self.subclauses:
            return True
        else:
            return False

    def wordCount(self):
        text = ' '.join(self.text)
        count = len(re.findall(r'\w+', text.strip()))
        return count

    def treeSize(self):
        size = 1
        for clauseID in self.subclauses:
            clause = Clause.clauseIndex[clauseID]
            size += clause.treeSize()
        return size

    def treeWeight(self):
        weight = len(" ".join(self.text))
        for clauseID in self.subclauses:
            clause = Clause.clauseIndex[clauseID]
            weight += clause.treeWeight()
        return weight

    def addSubClauseRef(self, clause):
        if clause in self.subclauses:
            logger.info(f'multiple addSubClause for {clause} in {self.structure}')
        self.subclauses.append(clause)

    def isSummarized(self):
        if len(self.summary) > 0:
            return True
        else:
            return False

    def summarize(self, summarizer, force = False, verbose = False):
        if self.isSummarized() and not force:
            return self.summary
        subtext = []
        for clauseID in self.subclauses:
            if clauseID in Clause.clauseIndex.keys():
                subtext.append("\n")
                clause = Clause.clauseIndex[clauseID]
                subtext += clause.summarize(summarizer, force, verbose)
        text = []
        text.append("# "+self.heading.getBestHeading())
        text += self.text
        text += subtext
        text = "\n".join(text)
        self.summary = summarizer.summarize(self, text.strip(), verbose)
        return self.summary

    def relate(self, parent, retriever):
        domain = retriever.domain
        if self.relationship == None:
            self.relationship = Relationship(self,parent,retriever)
        else:
            self.relationship.addRetriever(retriever)
        if len(self.subclauses)>0:
            for clauseID in self.subclauses:
                if clauseID in Clause.clauseIndex.keys():
                    clause = Clause.clauseIndex[clauseID]
                    clause.relate(self,retriever)
            self.relationship.levelUp(domain)
        self.relationship.relate(domain)
        
    def ingest(self, clauseingestor):
        clauseingestor.ingest_clause(self)
        for clauseID in self.subclauses:
            if clauseID in Clause.clauseIndex.keys():
                clause = Clause.clauseIndex[clauseID]
                clause.ingest(clauseingestor)

    def printText(self):
        print(self)
        for clauseID in self.subclauses:
            if clauseID in Clause.clauseIndex.keys():
                clause = Clause.clauseIndex[clauseID]
                clause.printText()

    def dumpTextData(self):
        myID = self.structure.ID
        md5hash = hashlib.md5(myID.encode('utf-8')).hexdigest()
        heading = self.heading.getBestHeading()
        text = '~'.join(self.text)
        entry = f"TEXT;{md5hash};{myID};{heading};\"{text}\""
        print(entry)
        for clauseID in self.subclauses:
            if clauseID in Clause.clauseIndex.keys():
                clause = Clause.clauseIndex[clauseID]
                clause.dumpTextData()
            else:
                print(f"clauseIndex key error for {clauseID}")

    def dumpHeadingData(self):
        myID = self.structure.ID
        md5hash = hashlib.md5(myID.encode('utf-8')).hexdigest()
        heading = self.heading.getBestHeading()
        clauseType = self.type
        if self.heading.state != 'loaded' and self.heading.state != 'parsed' :
            clauseType = self.type.upper()
        entry = f"TOC;{md5hash};{myID};{heading};{clauseType}"
        print(entry)
        for clauseID in self.subclauses:
            if clauseID in Clause.clauseIndex.keys():
                clause = Clause.clauseIndex[clauseID]
                clause.dumpHeadingData()
            else:
                print(f"clauseIndex key error for {clauseID}")
