# Standards Atlas Architecture

## Overview

Standards Atlas is a multi-layered framework that transforms international safety standards into navigable, collaborative knowledge bases. The architecture separates content generation, relationship mapping, and AI enhancement into distinct but integrated components.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Interface Layer                    │
├─────────────────────────────────────────────────────────────────┤
│  Web Browser    │    CLI Tools    │   IDE Integration          │
│  (HTML Output)  │  (Bash/Python)  │   (VS Code, etc.)          │
└─────────────────────────────────────────────────────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────┐
│                        Application Layer                       │
├─────────────────────────────────────────────────────────────────┤
│  standards-atlas │  linkItems    │  referenceItems │ intellidoc │
│  (Structure Gen) │  (Mapping)    │  (References)   │ (AI/ML)    │
└─────────────────────────────────────────────────────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────┐
│                        Processing Layer                        │
├─────────────────────────────────────────────────────────────────┤
│   Doorstop Engine   │   IntelliDoc AI    │   Data Processors   │
│   (Requirements)    │   (ML Analysis)    │   (CSV, YAML)       │
└─────────────────────────────────────────────────────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────┐
│                         Data Layer                             │
├─────────────────────────────────────────────────────────────────┤
│  Standard Defs  │  Mappings  │  Relations  │  Travelogues     │
│  (Structure)    │  (Links)   │  (AI Data)  │  (Examples)      │
└─────────────────────────────────────────────────────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────┐
│                        Infrastructure                          │
├─────────────────────────────────────────────────────────────────┤
│     Git VCS     │   RamaLama    │   Python Env   │   Doorstop   │
│   (Versioning)  │   (AI Models) │   (Runtime)     │   (Engine)   │
└─────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Structure Generation Engine

**Location**: `tools/standards-atlas` (Bash), `tools/standards-atlas.py` (Python)

**Purpose**: Generate complete doorstop document structures from standard definitions.

**Key Responsibilities**:
- Parse standard definition files from `data/` directory
- Create hierarchical doorstop documents
- Generate unique identifiers and cross-references
- Produce browsable HTML output
- Handle multi-volume standards (ISO 26262, IEC 61508)

**Data Flow**:
```
Standard Definition Files → Parser → Doorstop Documents → HTML Output
         ↓                    ↓              ↓              ↓
    data/IEC61508      Structure Tree   YAML Files    requirements/
    data/ISO26262      Clause Objects   Metadata      index.html
```

**Architecture Details**:
- **Input Processing**: Custom DSL for standard structure definitions
- **Hierarchy Management**: Multi-level clause numbering and relationships
- **ID Generation**: Deterministic UID creation with configurable digit lengths
- **Output Generation**: Doorstop-native YAML + HTML publishing

### 2. Cross-Standard Mapping Engine

**Location**: `tools/linkItems`

**Purpose**: Create bidirectional relationships between clauses across different standards.

**Key Responsibilities**:
- Process mapping definition files
- Create doorstop links between related clauses
- Support multiple relationship types (equivalence, similarity, etc.)
- Maintain bidirectional consistency

**Data Flow**:
```
Mapping Files → Link Processor → Doorstop Links → Updated Documents
      ↓              ↓               ↓                ↓
 data/mapping01  Relationship     YAML Updates    Cross-linked
 data/mapping02   Analysis        Link Objects     HTML Output
```

**Relationship Types**:
- **Equivalence**: Direct functional equivalents
- **Similarity**: Related but not identical requirements  
- **Hierarchy**: Parent-child relationships across standards
- **Context**: Clauses that provide relevant context

### 3. AI-Enhanced Analysis System (IntelliDoc)

**Location**: `tools/intellidoc`, `tools/IntelliDoc/`

**Purpose**: Apply AI/ML techniques to enhance standard structures and discover relationships.

#### 3.1 Knowledge Domain Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Knowledge Domain Layer                       │
├─────────────────────────────────────────────────────────────────┤
│   Automotive    │    Railway     │   Industrial   │   Marine    │
│   (ISO 26262)   │  (EN 50126/8/9)│  (IEC 61508)   │ (ISO 5083) │
└─────────────────────────────────────────────────────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────┐
│                     Document Tree Layer                        │
├─────────────────────────────────────────────────────────────────┤
│    Standard      │    Volume      │    Chapter     │   Clause   │
│    Series        │    Structure   │    Hierarchy   │   Objects  │
└─────────────────────────────────────────────────────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────┐
│                      Clause Analysis Layer                     │
├─────────────────────────────────────────────────────────────────┤
│   Text Analysis  │  Type Class.  │  Relationships │  Embeddings │
│   (Tokenization) │  (r,s,t,o,c)  │  (Semantic)    │  (Vectors) │
└─────────────────────────────────────────────────────────────────┘
```

#### 3.2 AI Components

**HeadingFactory**: Generates meaningful headings for unlabeled clauses
```python
# Workflow:
Text Input → LLM Prompt → Response Filtering → Heading Extraction → Storage
    ↓           ↓             ↓                 ↓                ↓
 Clause     "Create 3     Multiple         Regex Pattern    Alternative
 Content    word heading"  Attempts         Matching         Headings
```

**Summarizer**: Creates concise summaries of clause content
```python
# Workflow:
Clause Text → Context Prompt → LLM Generation → Summary Extraction → Caching
     ↓            ↓               ↓                ↓                 ↓
  Full Text   System Context   Response Text   Filtered Lines   JSON Store
```

**Relationship Mapper**: Discovers semantic connections between clauses
```python
# Workflow:
Text Embedding → Vector Search → Similarity Scoring → Relationship Validation
      ↓              ↓              ↓                    ↓
   Embedding      Vector DB      Cosine Distance    Cross-Domain Links
   Models         Storage        Calculations       Generation
```

### 4. Document Reference System

**Location**: `tools/referenceItems`

**Purpose**: Automatically link travelogue documents to relevant standard clauses.

**Key Responsibilities**:
- Scan travelogue documents for standard references
- Create automatic links to doorstop items
- Update references when standards change
- Maintain reference consistency

**Reference Pattern Matching**:
```regex
Standard References:
- ISO 26262-6:2018 5.4.1
- IEC 61508-3:2010 7.4.2  
- EN 50129:2003 4.3.2.1

Clause Patterns:
- [Standard]-[Part]:[Year] [Clause.Number]
- Auto-linked to corresponding doorstop UIDs
```

## Data Architecture

### 1. Standard Definition Format

**Location**: `data/[STANDARD_NAME]`

**Structure**:
```bash
# Metadata
name="ISO 26262"
parent="IEC61508"  
digits=12
partShift=0

# Structure Definition
structure=(
 "2018 1-0 1-1 1-2 1-3 1-t3.{1..185} 1-4"
 "2018 2-0 2-1 2-2 2-r2.2.{1..15} 2-3"
 # [year] [volume-][type][enum:]index[.{range}]
)

# Content Data (TOC and TEXT entries)
TOC;md5hash;identifier;title;type
TEXT;md5hash;identifier;heading;content
```

**Parsing Logic**:
- **Volume**: Multi-part standard sections (`1-`, `2-`)
- **Type**: `r`=requirement, `s`=scope, `t`=term, `o`=objective, `c`=clause
- **Enumeration**: Bash range expansion (`{1..185}`)
- **Hierarchy**: Dot notation for sub-clauses (`1.2.3.4`)

### 2. Relationship Mapping Format

**Location**: `data/mapping[NN]`

**Structure**:
```bash
# Mapping metadata
from=ISO26262
to=IEC61508
type=equivalence

# Relationship data
FROM_UID;context;description;TO_UID
# Creates bidirectional doorstop links
```

### 3. Vector Store Architecture

**Component**: `tools/IntelliDoc/VectorStore.py`

**Purpose**: Semantic search and similarity matching for relationship discovery.

**Architecture**:
```
Text Input → Tokenization → Embedding → Vector Storage → Similarity Search
     ↓           ↓            ↓             ↓              ↓
 Clause Text  Sentences   nomic-embed    Qdrant DB    Cosine Distance
 Processing   (NLTK)      Vectors        Index        Ranking
```

**Quality Metrics**:
1. **Self-Identification**: Clauses should match themselves (>90% target)
2. **Sibling Clustering**: Related clauses should group together
3. **Reciprocity**: Strong relationships should work bidirectionally

## Integration Architecture

### 1. Doorstop Integration

Standards Atlas uses [Doorstop](https://doorstop.readthedocs.io/) as its requirements management backbone:

**Benefits**:
- Industry-standard YAML format
- Git integration for version control
- HTML publishing capabilities
- Link validation and traceability
- Extensible attribute system

**Custom Enhancements**:
- Multi-standard document trees
- Custom attribute schemas for standards metadata
- Enhanced linking for cross-domain relationships
- Automated publishing workflows

### 2. RamaLama AI Integration

**Architecture**:
```
IntelliDoc → RamaLamaClient → RamaLama Server → Local Models
     ↓             ↓               ↓               ↓
  AI Requests  REST API       Model Engine    nemotron/llama
  Processing   Calls          Management      granite/etc.
```

**Model Management**:
- **Automatic Download**: Models fetched on first use
- **Server Lifecycle**: Automatic startup/shutdown
- **Resource Management**: Memory and CPU optimization
- **Model Selection**: Context-appropriate model choice

### 3. Git Workflow Integration

**Version Control Strategy**:
```
Source Code → Standards Atlas → Generated Output → Git Repository
     ↓              ↓               ↓                ↓
 data/ files    Processing       doorstop/        Version Control
 mappings       Engine           HTML output      Collaboration
```

**Collaboration Model**:
- **Source Control**: Structure definitions and mappings
- **Generated Content**: Published HTML and processed data
- **Community Contributions**: Shared structural knowledge
- **Branching**: Different standard versions and experiments

## Performance and Scalability

### 1. Processing Performance

**Structure Generation**:
- **Speed**: ~1000 clauses/second for structure creation
- **Memory**: ~100MB for complete standard sets
- **Parallelization**: Independent standard processing

**AI Processing**:
- **Heading Generation**: ~2-10 seconds per clause (model dependent)
- **Batch Processing**: Optimized for bulk operations
- **Caching**: Persistent storage of AI-generated content

### 2. Scalability Considerations

**Horizontal Scaling**:
- Independent standard processing
- Parallelizable AI operations  
- Distributed vector storage support

**Vertical Scaling**:
- Memory-efficient processing
- Streaming for large datasets
- Configurable resource limits

## Security and Legal Considerations

### 1. Copyright Compliance

**Architecture Ensures**:
- **No Content Storage**: Only structural metadata
- **Safe Sharing**: Community-driven enhancements
- **Legal Boundaries**: Clear separation of structure vs. content

### 2. Data Privacy

**AI Processing**:
- **Local Models**: No data sent to external services
- **Isolated Processing**: Self-contained analysis
- **Configurable**: Users control all AI operations

## Extension Points

### 1. New Standards Integration

**Process**:
1. Create standard definition file (`data/NEW_STANDARD`)
2. Define structure using DSL syntax
3. Add TOC/TEXT data if available
4. Run standards-atlas to generate

**Requirements**:
- Hierarchical clause numbering
- Consistent metadata format
- Optional: relationship mappings to existing standards

### 2. Custom AI Models

**Integration Points**:
- RamaLama model configuration
- Custom prompt engineering
- Alternative embedding models
- Enhanced relationship discovery

### 3. Output Format Extensions

**Current Support**:
- Doorstop YAML
- HTML publishing
- CSV exports
- JSON data dumps

**Extension Opportunities**:
- StrictDoc integration
- SPDX format support
- Custom web applications
- API endpoints

## Development Architecture

### 1. Code Organization

```
tools/
├── standards-atlas           # Main structure generator (Bash)
├── standards-atlas.py        # Python implementation
├── linkItems                 # Relationship processor
├── referenceItems           # Document referencer
├── intellidoc               # AI orchestrator
└── IntelliDoc/              # AI module library
    ├── RamalamaClient.py    # LLM integration
    ├── HeadingFactory.py    # Heading generation
    ├── Summarizer.py        # Content summarization
    ├── VectorStore.py       # Semantic search
    └── [other modules]      # Specialized components
```

### 2. Dependency Management

**Core Dependencies**:
- **Python 3.10+**: Runtime environment
- **Poetry**: Dependency management
- **Doorstop**: Requirements engine
- **RamaLama**: AI model management

**AI Dependencies**:
- **LlamaIndex**: Vector processing framework
- **NLTK**: Natural language processing
- **NumPy**: Numerical computations
- **Qdrant**: Vector database (optional)

### 3. Testing Strategy

**Component Testing**:
- Unit tests for core processing logic
- Integration tests for AI components
- End-to-end workflow validation

**Quality Assurance**:
- Type checking with mypy
- Code formatting with black
- Linting with ruff
- Documentation completeness

---

*This architecture supports Standards Atlas's mission to democratize safety standards through open, collaborative, and AI-enhanced knowledge sharing.*