# Getting Started with Standards Atlas

## Overview

Standards Atlas is a comprehensive framework for working with international safety standards. It provides:

- **Structure Navigation**: Browse standard hierarchies without copyright content
- **Cross-Standard Mapping**: Find relationships between different standards
- **AI-Enhanced Analysis**: Generate headings and discover semantic connections
- **Collaborative Framework**: Share structural knowledge openly

## Prerequisites

To use Standards Atlas, you need:
- **Python 3.10 or higher**
- **Poetry** (for dependency management)
- **Git** (doorstop requires git repositories)

Install Poetry if you don't have it:
```bash
curl -sSL https://install.python-poetry.org | python3 -
```

## Installation

1. **Clone the repository:**
```bash
git clone https://github.com/your-org/standards-atlas.git
cd standards-atlas
```

2. **Run the setup script:**
```bash
source setup.sh
```

This script will:
- Configure Poetry to use a local virtual environment
- Install all Python dependencies (including RamaLama, doorstop, etc.)
- Activate the virtual environment
- Apply necessary patches to doorstop

## Automatic Doorstop Patching

The setup script automatically applies patches to doorstop for Standards Atlas compatibility. The patch system:
- Detects your doorstop installation location
- Applies patches only if not already applied
- Uses a marker file to prevent duplicate patching

No manual patching is required - everything is handled automatically.

## Quick Start

### 1. Generate Standard Structures

Create the complete standards structure:
```bash
./tools/standards-atlas
```

This creates doorstop documents under `/tmp/standards-atlas` with structures for:
- IEC 61508 (Industrial Safety)
- ISO 26262 (Automotive Safety)  
- EN 50126/128/129 (Railway Safety)
- EN 50716 (Railway Applications)
- And more...

### 2. Publish to HTML

Generate browsable HTML documentation:
```bash
./tools/standards-atlas -t
```

### 3. Create Cross-References

Add automatic references to travelogue documents:
```bash
./tools/standards-atlas -l
```

### 4. Custom Output Directory

Use a different output directory:
```bash
./tools/standards-atlas -d /path/to/your/project
```

## Core Tools Overview

### standards-atlas (Main Tool)
The primary script for generating standard structures:

```bash
# Basic usage
./tools/standards-atlas

# With publishing and referencing
./tools/standards-atlas -t -l

# Skip recreation (update only)
./tools/standards-atlas -n

# Custom directory with CSV output
./tools/standards-atlas -d ~/my-project -c
```

**Options:**
- `-t` : Automatic publishing to HTML
- `-l` : Automatic referencing of travelogues  
- `-n` : No recreation of items (update only)
- `-d` : Specify output directory
- `-c` : Generate CSV for content processing

### linkItems
Creates relationships between standards:
```bash
./tools/linkItems /path/to/doorstop/root
```

Reads mapping files from `data/mapping*` and creates bidirectional links.

### referenceItems  
Automatically references clauses in travelogue documents:
```bash
./tools/referenceItems /path/to/doorstop/root
```

### intellidoc (AI-Enhanced)
AI-powered content analysis and enhancement:

```bash
# Generate missing headings
./tools/intellidoc -g

# Harvest headings from documents  
./tools/intellidoc -H

# Use specific model
./tools/intellidoc -l llama3.2:1b

# Interactive mode
./tools/intellidoc -i

# Bulk processing
./tools/intellidoc -b
```

**Key Features:**
- Automatic heading generation for unlabeled clauses
- Semantic relationship discovery
- Support for multiple AI models via RamaLama
- Interactive and batch processing modes

## Project Structure

Understanding the directory layout:

```
standards-atlas/
├── tools/                    # Main executable scripts
│   ├── standards-atlas      # Primary structure generator
│   ├── standards-atlas.py   # Python version
│   ├── intellidoc          # AI-enhanced analysis
│   ├── linkItems           # Cross-standard linking
│   └── IntelliDoc/         # AI module components
├── data/                    # Standard definitions
│   ├── IEC61508           # Industrial safety standard
│   ├── ISO26262           # Automotive safety standard
│   ├── EN50126            # Railway safety standards
│   ├── mapping01          # Cross-standard relationships
│   └── relations.csv      # Pre-calculated relationships
├── docs/                   # Documentation
├── travelogue/            # Example usage documents
└── cfg/                   # Configuration and patches
```

## Working with Standards

### 1. Structure Generation

The heart of Standards Atlas is generating navigable structures:

```bash
# Generate all standards
./tools/standards-atlas -d ~/safety-project

# Navigate to output directory
cd ~/safety-project

# Browse with your web browser
firefox requirements/index.html
```

### 2. Cross-Standard Mapping

Find relationships between different domains:

```bash
# After generating structures
./tools/linkItems ~/safety-project

# This creates links like:
# ISO 26262-6:2018 5.4.1 ↔ IEC 61508-3:2010 7.4.2
```

### 3. AI-Enhanced Workflows

Generate meaningful headings for unlabeled clauses:

```bash
# First, place your standard documents as Markdown in:
mkdir ~/safety-project/markdown
# Add: EN50126.md, ISO26262-1.md, etc.

# Generate headings
./tools/intellidoc -g -c ~/safety-project/csv/heading-data.csv

# Process interactively
./tools/intellidoc -i
```

## Advanced Usage

### Custom Standards

Add your own standards by creating data files:

```bash
# Create data/MY_STANDARD with structure definitions
# See data/IEC61508 for format examples
```

### Relationship Discovery

Use AI to find semantic connections:

```bash
# Generate relationship mappings
./tools/intellidoc -r csv/relations.csv

# Apply the discovered relationships  
./tools/linkItems ~/safety-project
```

### Travelogue Documents

Create navigable documents that reference standards:

```bash
# See examples in travelogue/ directory
# Documents automatically link to standard clauses
# Use ./tools/referenceItems to update references
```

## Output and Results

After running the tools, you'll have:

1. **Browsable HTML**: Complete standard structures in web format
2. **Doorstop YAML**: Machine-readable requirement documents
3. **CSV Exports**: Data for further processing
4. **Cross-References**: Links between related clauses
5. **AI-Generated Content**: Enhanced headings and summaries

## Integration with Other Tools

Standards Atlas outputs are compatible with:

- **Doorstop**: Native format for requirements management
- **StrictDoc**: Alternative documentation tool
- **SPDX**: For software bill of materials integration  
- **Custom Tools**: Via CSV exports and YAML access

## Troubleshooting

### Common Issues

**Setup Problems:**
```bash
# Ensure Poetry is installed
poetry --version

# Re-run setup if needed
source setup.sh
```

**Doorstop Errors:**
```bash
# Check git repository
git status

# Ensure doorstop patch applied
ls ~/.local/lib/python*/site-packages/doorstop/.doorstop_custom_patch_applied
```

**AI Model Issues:**
```bash
# Test RamaLama integration
python test_ramalama.py

# Use smaller model if memory issues
./tools/intellidoc -l llama3.2:1b
```

**Permission Errors:**
```bash
# Ensure output directory is writable
chmod +w /tmp/standards-atlas

# Use custom directory if needed
./tools/standards-atlas -d ~/standards-output
```

## Next Steps

1. **Explore Examples**: Check the `travelogue/` directory for usage examples
2. **Read Documentation**: See `docs/` for detailed information
3. **Try AI Features**: Experiment with `intellidoc` capabilities
4. **Create Mappings**: Develop relationships between your standards of interest
5. **Contribute**: Share your structural knowledge and improvements

## Support and Community

- **Documentation**: See `docs/` directory for detailed guides
- **Examples**: Study the `travelogue/` documents  
- **Issues**: Report problems via project repository
- **Contributions**: Submit structural data, mappings, and improvements

---

*Standards Atlas bridges the gap between expensive, closed standards and open, collaborative safety engineering.*