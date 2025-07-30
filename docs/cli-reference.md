# CLI Reference Guide

This guide provides comprehensive documentation for all Standards Atlas command-line tools.

## Overview

Standards Atlas provides five main command-line tools:

| Tool | Purpose | Language |
|------|---------|----------|
| [`standards-atlas`](#standards-atlas) | Main structure generator | Bash |
| [`intellidoc`](#intellidoc) | AI-enhanced analysis | Python |
| [`linkItems`](#linkitems) | Cross-standard mapping | Bash |
| [`referenceItems`](#referenceitems) | Document referencing | Python |
| [`relator`](#relator) | Relationship processing | Python |

## standards-atlas

**Main structure generator that creates complete doorstop documents from standard definitions.**

### Synopsis
```bash
./tools/standards-atlas [OPTIONS]
```

### Description
The primary tool for generating Standards Atlas content. Reads standard definition files from the `data/` directory and creates complete doorstop document structures with hierarchical organization, unique identifiers, and optional HTML publishing.

### Options

| Option | Argument | Default | Description |
|--------|----------|---------|-------------|
| `-i` | - | Off | Enable readable index format for clause IDs |
| `-t` | - | Off | Enable automatic HTML publishing |
| `-n` | - | Off | No recreation - skip creating doorstop items (update only) |
| `-b` | - | Off | Basic content only - minimal structure generation |
| `-c` | - | Off | Generate CSV list of all TOC entries for processing |
| `-l` | - | Off | Enable automatic reference linking to travelogue documents |
| `-d` | `<path>` | `/tmp/standards-atlas` | Output directory for doorstop files |
| `-g` | `<gitrepo>` | - | Git repository URL *(not implemented)* |
| `-r` | `<MYREQ>` | `SOHP` | Additional requirements document name |
| `-p` | `<STANDARD>` | `EN50716` | Parent standard for additional requirements |
| `-h` | - | - | Show help message |

### Examples

**Basic usage:**
```bash
# Generate all standards in default location
./tools/standards-atlas

# Generate with HTML publishing
./tools/standards-atlas -t

# Generate with both publishing and referencing
./tools/standards-atlas -t -l
```

**Custom configuration:**
```bash
# Use custom output directory
./tools/standards-atlas -d ~/my-safety-project

# Generate CSV for further processing
./tools/standards-atlas -c -d ~/project

# No recreation, just update references and publish
./tools/standards-atlas -n -t -l -d ~/project
```

**Advanced usage:**
```bash
# Custom requirements with specific parent
./tools/standards-atlas -r "MY_CUSTOM_REQ" -p "ISO26262" -d ~/project

# Basic content only with readable indices
./tools/standards-atlas -b -i -d ~/minimal-project
```

### Supported Standards
- **IEC 61508** (Industrial Safety) - 8 volumes
- **ISO 26262** (Automotive Safety) - 12 volumes  
- **PAS 8926** (Automotive Extension)
- **EN 50126** (Railway Safety - Reliability, Availability, Maintainability, Safety)
- **EN 50129** (Railway Safety - Communication, Signalling and Processing Systems)
- **EN 50716** (Railway Applications - Cybersecurity)

### Output Structure
```
<output_directory>/
├── requirements/           # Doorstop documents
│   ├── index.html         # Main index (if -t used)
│   ├── IEC61508/         # Standard documents
│   ├── ISO26262/
│   └── [other standards]/
├── csv/                   # CSV exports (if -c used)
│   └── heading-data.csv
├── travelogue/           # Referenced documents (if -l used)
└── [generated files]
```

### Exit Codes
- `0` - Success
- `1` - Error (missing data directory, creation failure, etc.)

---

## intellidoc

**AI-powered analysis tool for enhancing standard structures with machine learning.**

### Synopsis
```bash
./tools/intellidoc [OPTIONS]
```

### Description
Advanced tool that applies AI/ML techniques to standard documents. Generates meaningful headings for unlabeled clauses, discovers semantic relationships, and processes markdown documents to enhance structural data.

### Options

| Option | Argument | Default | Description |
|--------|----------|---------|-------------|
| `-H`, `--harvest` | - | Off | Harvest mode - extract headings from MD documents |
| `-g`, `--generate` | - | Off | Generate mode - create missing headings with AI |
| `-l`, `--llm-model` | `<model>` | `nemotron` | LLM model for text generation |
| `-c`, `--content` | `<file>` | `csv/heading-data.csv` | Content structure CSV file |
| `-w`, `--weights` | `<file>` | `csv/weights.csv` | Sentence weights CSV file |
| `-r`, `--relations` | `<file>` | `csv/relations.csv` | Clause relations CSV file |
| `-d`, `--refmap` | `<file>` | `csv/uid-ref-map.csv` | UID reference mapping file |
| `-i`, `--interactive` | - | Off | Interactive heading generation mode |
| `-b`, `--bulk` | - | Off | Bulk processing mode for headings |

### Supported Models

| Model | Speed | Quality | Memory | Best Use |
|-------|-------|---------|--------|----------|
| `llama3.2:1b` | Fast | Good | Low | Interactive, testing |
| `llama3.1` | Fast | Good | Medium | General purpose |
| `nemotron` | Slow | Excellent | High | Production, bulk processing |
| `granite3-moe` | Medium | Good | Medium | Alternative option |
| `granite3-dense` | Medium | Good | Medium | Alternative option |

### Workflow Modes

#### 1. Harvest Mode (`-H`)
Extract existing headings from markdown documents:
```bash
# Extract headings from markdown files
./tools/intellidoc -H -c my-project/csv/heading-data.csv
```

#### 2. Generate Mode (`-g`)
AI-powered heading generation for unlabeled clauses:
```bash
# Generate headings with default model
./tools/intellidoc -g

# Use faster model for testing
./tools/intellidoc -g -l llama3.2:1b

# Use best quality model
./tools/intellidoc -g -l nemotron
```

#### 3. Interactive Mode (`-i`)
Manual selection of AI-generated headings:
```bash
# Interactive heading selection
./tools/intellidoc -i -l llama3.1
```

#### 4. Bulk Mode (`-b`)
Automated bulk processing:
```bash
# Process all clauses in bulk
./tools/intellidoc -b -l nemotron
```

### Examples

**Basic AI enhancement:**
```bash
# Generate missing headings with default model
./tools/intellidoc -g

# Use specific model for generation
./tools/intellidoc -g -l llama3.2:1b
```

**Document processing:**
```bash
# Harvest headings from existing documents
./tools/intellidoc -H -c project/csv/heading-data.csv

# Process with custom data files
./tools/intellidoc -g \
  -c project/csv/content.csv \
  -w project/csv/weights.csv \
  -r project/csv/relations.csv
```

**Advanced workflows:**
```bash
# Interactive generation with fast model
./tools/intellidoc -i -l llama3.1

# Bulk processing with high-quality model
./tools/intellidoc -b -l nemotron

# Combined harvest and generate
./tools/intellidoc -H -g -l nemotron
```

### Input Requirements

**Markdown Documents**: Place in `markdown/` directory
```
markdown/
├── IEC61508.md
├── ISO26262-1.md
├── ISO26262-2.md
└── [other standard documents]
```

**CSV Structure Files**: Generated by `standards-atlas -c`
- Content structure definitions
- Clause weight calculations  
- Relationship mappings
- UID reference maps

### Output

**Generated Headings**: Added to clause objects and cached
**Enhanced Structure**: Updated doorstop documents
**Analysis Data**: CSV files with AI-generated content
**Log Files**: `Tokenizer.log` with processing details

---

## linkItems

**Cross-standard relationship processor that creates bidirectional links between related clauses.**

### Synopsis
```bash
./tools/linkItems [OPTIONS] [DIRECTORY]
```

### Description
Processes relationship mapping files to create doorstop links between clauses in different standards. Reads mapping definitions and establishes bidirectional connections for cross-domain navigation.

### Options

| Option | Argument | Default | Description |
|--------|----------|---------|-------------|
| `-i` | - | Off | Enable readable index format |
| `-d` | `<path>` | `/tmp/standards-atlas` | Path to standards atlas directory |
| `-h` | - | - | Show help message |

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `DIRECTORY` | No | Standards atlas directory (alternative to `-d`) |

### Examples

**Basic usage:**
```bash
# Process mappings in default directory
./tools/linkItems

# Process mappings in custom directory
./tools/linkItems -d ~/my-safety-project

# Alternative syntax
./tools/linkItems ~/my-safety-project
```

**With readable indices:**
```bash
# Use human-readable clause identifiers
./tools/linkItems -i -d ~/project
```

### Input Files

**Mapping Files**: Located in `data/mapping*`
```
data/
├── mapping01    # Automotive ↔ Industrial
├── mapping02    # Railway ↔ Industrial  
├── mapping03    # Custom mappings
└── mapping04    # Additional relationships
```

**Mapping Format**:
```bash
# Header
from=ISO26262
to=IEC61508
type=equivalence

# Relationship data
ISO26262-6-007;Software verification;Verification methods;IEC61508-3-047
ISO26262-6-008;Software testing;Testing procedures;IEC61508-3-048
```

### Output

**Doorstop Links**: Bidirectional connections between clauses
**Updated HTML**: Enhanced navigation between standards
**Link Validation**: Automatic verification of relationship integrity

### Relationship Types
- **Equivalence**: Direct functional equivalents
- **Similarity**: Related but different requirements
- **Context**: Relevant background information
- **Hierarchy**: Structural relationships

---

## referenceItems

**Document reference processor that automatically links travelogue documents to standard clauses.**

### Synopsis
```bash
./tools/referenceItems <ATLAS_PATH>
```

### Description
Scans travelogue documents for standard references and creates automatic links to corresponding doorstop items. Updates references when standards change and maintains consistency across documentation.

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `ATLAS_PATH` | Yes | Path to the standards atlas directory |

### Examples

**Basic usage:**
```bash
# Process references in specified directory
./tools/referenceItems ~/my-safety-project

# Process references in default location
./tools/referenceItems /tmp/standards-atlas
```

### Input

**Travelogue Documents**: Located in `travelogue/` directory
```
travelogue/
├── ISO-IEC-DocumentationManagement.md
├── Proven-In-Use-Argument.md
├── Requirements-Basic-Integrity-(SIL0)-according-to-EN-50716.md
└── [other example documents]
```

**Reference Patterns**: Standard clause references in documents
```markdown
According to ISO 26262-6:2018 5.4.1, software verification...
IEC 61508-3:2010 7.4.2 specifies that...
EN 50129:2003 4.3.2.1 requires...
```

### Output

**Updated Travelogues**: Documents with automatic links
```markdown
According to [ISO 26262-6:2018 5.4.1](../requirements/ISO26262.html#ISO26262-6-007), software verification...
```

**Reference Mapping**: Updated cross-reference database
**Validation Reports**: Missing or broken reference detection

### Supported Reference Formats
- `STANDARD-PART:YEAR CLAUSE.NUMBER`
- `STANDARD:YEAR CLAUSE.NUMBER` (single-part standards)
- `STANDARD CLAUSE.NUMBER` (without year)

---

## relator

**Advanced relationship processor for semantic analysis and mapping generation.**

### Synopsis
```bash
./tools/relator <ATLAS_PATH> <MAP_PATH>
```

### Description
Processes semantic relationships between clauses using AI-generated analysis data. Creates enhanced relationship mappings based on vector similarity and clustering analysis.

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `ATLAS_PATH` | Yes | Path to the standards atlas directory |
| `MAP_PATH` | Yes | Path to the UID reference mapping file |

### Examples

**Basic usage:**
```bash
# Process relationships with default map
./tools/relator ~/project ~/project/csv/uid-ref-map.csv

# Use custom mapping file
./tools/relator /tmp/standards-atlas /tmp/standards-atlas/csv/custom-map.csv
```

### Input Requirements

**Relations Data**: `data/relations.csv` with AI-generated scores
**UID Mapping**: Reference mapping between clause IDs and doorstop UIDs
**Atlas Structure**: Complete doorstop document tree

### Processing

**Relationship Scoring**: Semantic similarity analysis
**Bidirectional Validation**: Ensure relationship consistency
**Quality Metrics**: Self-identification and clustering analysis
**Score Thresholds**: Filter low-quality relationships

### Output

**Enhanced Mappings**: High-quality relationship data
**Validation Reports**: Relationship quality metrics
**Bidirectional Links**: Consistent cross-references

---

## Common Workflows

### 1. Complete Structure Generation

```bash
# Generate complete standards atlas
./tools/standards-atlas -t -l -d ~/safety-project

# Add cross-standard relationships
./tools/linkItems ~/safety-project

# Update document references
./tools/referenceItems ~/safety-project
```

### 2. AI-Enhanced Analysis

```bash
# Generate basic structure with CSV export
./tools/standards-atlas -c -d ~/project

# Generate AI headings
./tools/intellidoc -g -l nemotron -c ~/project/csv/heading-data.csv

# Process semantic relationships
./tools/relator ~/project ~/project/csv/uid-ref-map.csv

# Apply relationship mappings
./tools/linkItems ~/project

# Final publishing
./tools/standards-atlas -n -t -l -d ~/project
```

### 3. Interactive Development

```bash
# Initial structure
./tools/standards-atlas -d ~/dev-project

# Interactive heading generation
./tools/intellidoc -i -l llama3.1

# Manual relationship review
./tools/linkItems -i ~/dev-project

# Test and iterate
./tools/standards-atlas -n -t -d ~/dev-project
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PYTHONPATH` | - | Include project tools directory |
| `RAMALAMA_MODEL_PATH` | - | Custom model storage location |
| `DOORSTOP_CONFIG` | - | Custom doorstop configuration |

## Error Handling

### Common Exit Codes
- `0` - Success
- `1` - General error (file not found, permission denied)
- `2` - Invalid arguments or usage
- `3` - Processing error (AI model failure, etc.)

### Debugging
- Use `-v` or `--verbose` where available
- Check log files: `Tokenizer.log`, doorstop logs
- Verify input file formats and paths
- Test with smaller datasets first

## Performance Considerations

### Resource Usage
- **standards-atlas**: ~100MB memory, fast execution
- **intellidoc**: 2-8GB memory (model dependent), slow execution
- **linkItems**: ~50MB memory, fast execution
- **referenceItems**: ~50MB memory, fast execution

### Optimization Tips
- Use smaller AI models for development (`llama3.2:1b`)
- Process standards incrementally for large datasets
- Cache AI-generated content to avoid regeneration
- Use bulk mode for production AI processing

---

*For detailed examples and tutorials, see the [Getting Started Guide](getting-started.md) and [Architecture Documentation](architecture.md).*