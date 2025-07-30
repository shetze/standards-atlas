# Standards Atlas

**Democratizing Safety Standards Through Open Collaboration**

[![License: LGPL-3.0](https://img.shields.io/badge/License-LGPL%203.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![Poetry](https://img.shields.io/badge/dependency-poetry-blue.svg)](https://python-poetry.org)

Standards Atlas bridges the gap between expensive, closed international safety standards and the open-source community. It provides the structural framework of standards documents—table of contents, clause numbering, hierarchies—that can be freely shared, navigated, and enhanced collaboratively.

## 🎯 What Standards Atlas Does

- **📚 Structure Navigation**: Browse complete hierarchies of major safety standards without copyright content
- **🔗 Cross-Standard Mapping**: Discover relationships between clauses across different standards domains  
- **🤖 AI-Enhanced Analysis**: Generate meaningful headings and find semantic connections using local LLMs
- **🌐 Collaborative Framework**: Share structural knowledge and safety arguments openly
- **⚡ Requirements Management**: Leverage doorstop for professional requirements traceability

## 🏗️ Supported Standards

| Domain | Standards | Coverage |
|--------|-----------|----------|
| **Industrial** | IEC 61508 | Complete structure (8 volumes) |
| **Automotive** | ISO 26262, PAS 8926 | Complete structure (12 volumes) |
| **Railway** | EN 50126/128/129, EN 50716, EN 50657 | Complete structure |
| **Information Security** | IEC 11889 | Basic structure |
| **Marine** | ISO 5083 | Basic structure |

## 🚀 Quick Start

### Installation
```bash
# Clone the repository
git clone https://github.com/your-org/standards-atlas.git
cd standards-atlas

# One-command setup (installs all dependencies)
source setup.sh
```

### Generate Your First Atlas
```bash
# Create complete standards structure
./tools/standards-atlas -t -l

# Browse the results
firefox /tmp/standards-atlas/requirements/index.html
```

### Explore Cross-Standard Relationships
```bash
# Generate structures in custom directory
./tools/standards-atlas -d ~/my-safety-project

# Add cross-standard links
./tools/linkItems ~/my-safety-project

# Browse connected standards
firefox ~/my-safety-project/requirements/index.html
```

## 🛠️ Core Tools

### standards-atlas
Main structure generator for all supported standards
```bash
./tools/standards-atlas          # Basic generation
./tools/standards-atlas -t       # With HTML publishing  
./tools/standards-atlas -l       # With reference linking
```

### intellidoc  
AI-powered content analysis and enhancement
```bash
./tools/intellidoc -g           # Generate missing headings
./tools/intellidoc -i           # Interactive mode
./tools/intellidoc -l llama3.2:1b  # Use specific AI model
```

### linkItems
Creates bidirectional relationships between standards
```bash
./tools/linkItems /path/to/project
```

### referenceItems
Automatically links travelogue documents to standard clauses
```bash
./tools/referenceItems /path/to/project
```

## 🧠 AI Integration

Standards Atlas uses **RamaLama** for local LLM operations:

- **Automatic Model Management**: Downloads and manages AI models automatically
- **Multiple Model Support**: Nemotron, Llama 3.2, Granite, and more
- **Smart Resource Management**: Automatic server startup/shutdown
- **Enhanced Analysis**: Generate headings, summaries, and discover semantic relationships

```python
# Example: Using AI to enhance standards
from tools.IntelliDoc.RamalamaClient import RamaLama

llm = RamaLama("nemotron")
heading = llm.query("Create a 3-word heading for: Software verification...")
```

## 📁 Project Structure

```
standards-atlas/
├── tools/                    # Executable scripts and AI modules
│   ├── standards-atlas      # Main structure generator (bash)
│   ├── standards-atlas.py   # Python version  
│   ├── intellidoc          # AI-enhanced analysis
│   ├── linkItems           # Cross-standard linking
│   ├── referenceItems      # Document referencing
│   └── IntelliDoc/         # AI module components
├── data/                    # Standard definitions and mappings
│   ├── IEC61508           # Industrial safety standard structure
│   ├── ISO26262           # Automotive safety standard structure
│   ├── EN50126            # Railway safety standards structure
│   ├── mapping01          # Cross-standard relationship definitions
│   └── relations.csv      # Pre-calculated semantic relationships
├── docs/                   # Comprehensive documentation
├── travelogue/            # Example navigable documents
└── cfg/                   # Configuration and patches
```

## 🌟 Key Features

### Open Structure, Closed Content
- ✅ **Free**: Complete clause hierarchies and numbering
- ✅ **Legal**: No copyright content, only structural metadata
- ✅ **Collaborative**: Community-driven enhancements
- ❌ **Not Included**: Actual standard text (copyright protected)

### Cross-Standard Intelligence
- **Semantic Mapping**: AI discovers relationships between standards
- **Domain Bridging**: Connect automotive ↔ railway ↔ industrial safety
- **Gap Analysis**: Identify missing coverage between standards
- **Argument Reuse**: Transfer safety cases across domains

### Professional Integration
- **Doorstop Compatible**: Industry-standard requirements management
- **Git Integration**: Version control for all structural data
- **HTML Export**: Professional browsable documentation
- **CSV Export**: Data analysis and custom tool integration

## 📖 Documentation

| Document | Purpose |
|----------|---------|
| [Getting Started](docs/getting-started.md) | Installation and basic usage |
| [IntelliDoc Guide](docs/intellidoc.md) | AI-powered features |
| [Data Formats](docs/data-formats.md) | Structure definitions and mappings |
| [Relationship Mapping](docs/relationship-mapping.md) | Cross-standard connections |
| [RamaLama Migration](docs/ramalama-migration-guide.md) | AI backend transition |

## 🎯 Use Cases

### For Open Source Projects
- **Engage with Safety**: Work with standards without expensive licenses
- **Build Safety Arguments**: Create reusable safety cases
- **Compliance Mapping**: Understand requirements across domains

### For Safety Engineers  
- **Navigate Standards**: Browse complete structures efficiently
- **Find Relationships**: Discover connections between standards
- **Transfer Knowledge**: Reuse expertise across domains

### For Researchers
- **Analyze Standards**: Study structural patterns and relationships  
- **Develop Tools**: Build on open structural data
- **Semantic Research**: Explore AI-driven standards analysis

### For Organizations
- **Training**: Teach standards structure without license costs
- **Gap Analysis**: Identify coverage differences between standards
- **Process Development**: Build on proven structural frameworks

## 🤝 Contributing

We welcome contributions of:

- **Structural Data**: Additional standards, corrections, improvements
- **Relationship Mappings**: Cross-standard connections and insights
- **Travelogue Documents**: Example usage and safety arguments
- **Tool Enhancements**: Better AI models, analysis features
- **Documentation**: Tutorials, guides, and examples

See our [Contributing Guide](CONTRIBUTING.md) for details.

## 📜 License

Standards Atlas is licensed under [LGPL-3.0](LICENSE), ensuring:
- ✅ **Free Use**: Personal and commercial applications
- ✅ **Open Innovation**: Collaborative development  
- ✅ **Legal Clarity**: No copyright conflicts with standards bodies
- ✅ **Community Growth**: Shared knowledge benefits everyone

## 🙏 Acknowledgments

- **[Doorstop](https://doorstop.readthedocs.io/)**: Foundation for requirements management
- **[RamaLama](https://github.com/containers/ramalama)**: Local LLM integration
- **Standards Communities**: Inspiration for open collaboration in safety
- **Open Source Movement**: Making critical knowledge accessible

## 🔗 Related Projects

- **[Doorstop](https://github.com/doorstop-dev/doorstop)**: Requirements management tool
- **[StrictDoc](https://strictdoc.readthedocs.io/)**: Alternative documentation framework  
- **[SPDX](https://spdx.dev/)**: Software package data exchange

---

**Standards Atlas**: *Democratizing safety standards through open collaboration*

> *"In the high-walled world of international standards, Standards Atlas opens doors to collaborative safety engineering."*
