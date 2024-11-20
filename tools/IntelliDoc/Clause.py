import re
import logging
import hashlib

logger = logging.getLogger(__name__)

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
    def __init__(self, clauseID, clauseHeading = 'Clause', clauseType = 'c', docType = 'standard', domain = 'generic'):
        self.structure = ClauseID(clauseID, docType)
        self.type = clauseType
        self.heading = ClauseHeading(clauseHeading)
        self.domain = domain
        self.keywords = []
        self.subclauses = []
        self.text = []
        self.summary = []

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
                'u' : 'text',
                'r' : 'requirement',
                's' : 'scope definition',
                'o' : 'objective',
                't' : 'term definition',
                'c' : 'clause',
                'x' : 'root',
                }
        return typedict[self.type]

    def id(self):
        return self.structure.ID

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

    def getText(self):
        text = ' '.join(self.text)
        return text.strip()

    def parentID(self):
        return self.structure.parentID()

    def hasSubClauseRef(self, clauseID):
        if clauseID in self.subclauses:
            return True
        else:
            return False

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
