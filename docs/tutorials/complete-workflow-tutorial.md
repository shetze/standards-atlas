# Complete Workflow Tutorial

This tutorial walks through a complete Standards Atlas workflow, from initial setup to advanced AI-enhanced analysis. You'll learn to create cross-standard mappings, generate AI headings, and build navigable safety documentation.

## Scenario: Creating a Multi-Domain Safety Reference

**Goal**: Create a comprehensive safety reference that maps requirements between automotive (ISO 26262), railway (EN 50129), and industrial (IEC 61508) standards.

**Time Required**: 2-3 hours (including AI processing)

**Prerequisites**: 
- Standards Atlas installed (`source setup.sh` completed)
- Basic familiarity with command line
- Optional: Standard documents in PDF/Markdown format

## Step 1: Project Setup and Basic Structure

### 1.1 Create Project Directory

```bash
# Create a dedicated project directory
mkdir ~/multi-domain-safety
cd ~/multi-domain-safety

# Verify Standards Atlas installation
ls ~/standards-atlas/tools/
# Should show: standards-atlas, intellidoc, linkItems, etc.
```

### 1.2 Generate Initial Structure

```bash
# Generate complete standards structure with HTML output
~/standards-atlas/tools/standards-atlas -t -d $(pwd)

# This creates:
# - requirements/ directory with all standard structures
# - Doorstop YAML files for each standard
# - HTML index for browsing
```

**Expected Output**:
```
Creating /home/user/multi-domain-safety
Generating IEC61508 structure...
Generating ISO26262 structure...
Generating EN50126 structure...
Generating EN50129 structure...
Publishing HTML documentation...
✓ Structure generation complete
```

### 1.3 Explore Generated Structure

```bash
# View the project structure
ls -la
# requirements/  - Main doorstop documents
# .doorstop      - Doorstop configuration

# Browse standards in web browser
firefox requirements/index.html
# Or: google-chrome requirements/index.html
```

**Navigation Tips**:
- Click on standard names to browse hierarchies
- Use browser search (Ctrl+F) to find specific clauses
- Notice that many clauses have generic titles like "REQUIREMENT"

## Step 2: Cross-Standard Relationship Mapping

### 2.1 Apply Existing Mappings

```bash
# Create relationships between standards using predefined mappings
~/standards-atlas/tools/linkItems $(pwd)

# This processes mapping files from data/mapping01, mapping02, etc.
# Creates bidirectional links between related clauses
```

### 2.2 Verify Relationships

```bash
# Regenerate HTML to include new links
~/standards-atlas/tools/standards-atlas -n -t -d $(pwd)

# Browse updated documentation
firefox requirements/index.html
```

**What to Look For**:
- Links between related clauses across standards
- Cross-references in clause descriptions
- Navigation paths between automotive ↔ railway ↔ industrial

### 2.3 Explore Cross-Domain Connections

**Example Navigation**:
1. Open `ISO26262` (Automotive)
2. Navigate to Part 6 (Software verification)
3. Look for links to `IEC61508` (Industrial) equivalents
4. Follow links to see related `EN50129` (Railway) requirements

## Step 3: AI-Enhanced Heading Generation

### 3.1 Prepare for AI Processing

```bash
# Generate CSV data for AI processing
~/standards-atlas/tools/standards-atlas -c -d $(pwd)

# This creates csv/ directory with:
# - heading-data.csv (structure information)
# - uid-ref-map.csv (reference mappings)
```

### 3.2 Test AI Integration

```bash
# Test with a small, fast model first
cd ~/multi-domain-safety
~/standards-atlas/tools/intellidoc -g -l llama3.2:1b

# This will:
# - Download the model (first time only)
# - Generate headings for unlabeled clauses
# - Take 10-20 minutes for complete processing
```

**Monitor Progress**:
```bash
# In another terminal, watch the log
tail -f Tokenizer.log
```

### 3.3 Production-Quality Heading Generation

```bash
# Use high-quality model for final results
~/standards-atlas/tools/intellidoc -g -l nemotron

# This process takes 1-2 hours but produces much better headings
# Progress indicators show current clause being processed
```

**Performance Tips**:
- Use `llama3.2:1b` for development/testing
- Use `nemotron` for production-quality results
- The system automatically manages model servers
- Processing can be interrupted and resumed

### 3.4 Review Generated Headings

```bash
# Regenerate structure with new headings
~/standards-atlas/tools/standards-atlas -n -t -d $(pwd)

# Browse updated documentation
firefox requirements/index.html
```

**Before/After Comparison**:
- **Before**: "ISO 26262-6:2018 5.4.1 REQUIREMENT"
- **After**: "ISO 26262-6:2018 5.4.1 Software Verification Methods"

## Step 4: Advanced Document Integration

### 4.1 Add Travelogue Documents

```bash
# Copy example travelogue documents
cp -r ~/standards-atlas/travelogue/* ~/multi-domain-safety/
ls travelogue/
# Shows example documents with standard references
```

### 4.2 Process Document References

```bash
# Automatically link travelogue documents to standards
~/standards-atlas/tools/referenceItems $(pwd)

# This:
# - Scans documents for standard references
# - Creates automatic links to doorstop items
# - Updates all references consistently
```

### 4.3 Final Publishing

```bash
# Generate final output with all enhancements
~/standards-atlas/tools/standards-atlas -n -t -l -d $(pwd)

# Browse complete system
firefox requirements/index.html
```

## Step 5: Custom Document Processing (Optional)

### 5.1 Add Your Own Documents

If you have actual standard documents in PDF format:

```bash
# Create markdown directory
mkdir markdown

# Convert PDFs to Markdown (example with pandoc)
pandoc "ISO 26262-6.pdf" -o markdown/ISO26262-6.md
pandoc "IEC 61508-3.pdf" -o markdown/IEC61508-3.md

# Note: PDF conversion quality varies
# Manual cleanup may be needed
```

### 5.2 Extract Headings from Documents

```bash
# Use harvest mode to extract existing headings
~/standards-atlas/tools/intellidoc -H

# This extracts headings from markdown documents
# Overwrites generic headings with actual document headings
```

### 5.3 Iterative Improvement

```bash
# Combine harvest and generate modes
~/standards-atlas/tools/intellidoc -H -g -l nemotron

# This:
# 1. Extracts existing headings where available
# 2. Generates headings for missing clauses
# 3. Produces the highest quality results
```

## Step 6: Semantic Relationship Discovery

### 6.1 Generate Advanced Relationships

```bash
# Process semantic relationships (requires previous AI processing)
~/standards-atlas/tools/relator $(pwd) $(pwd)/csv/uid-ref-map.csv

# This analyzes AI-generated content for semantic similarities
# Creates additional relationship mappings
```

### 6.2 Apply Discovered Relationships

```bash
# Apply newly discovered relationships
~/standards-atlas/tools/linkItems $(pwd)

# Regenerate with enhanced relationships
~/standards-atlas/tools/standards-atlas -n -t -d $(pwd)
```

## Step 7: Validation and Quality Assurance

### 7.1 Structure Validation

```bash
# Validate doorstop structure
cd requirements
doorstop validate

# Check for broken links or inconsistencies
# Fix any reported issues
```

### 7.2 Content Review

**Manual Review Checklist**:
- [ ] All major standards represented
- [ ] Cross-references working correctly
- [ ] AI-generated headings meaningful
- [ ] Travelogue documents properly linked
- [ ] HTML navigation functional

### 7.3 Export and Backup

```bash
# Export final data
cd ~/multi-domain-safety

# Create backup archive
tar -czf multi-domain-safety-$(date +%Y%m%d).tar.gz .

# Export data for other tools
doorstop export requirements standards-export.csv
```

## Results and Usage

### What You've Created

After completing this tutorial, you have:

1. **Complete Standard Structures**: Full hierarchical view of major safety standards
2. **Cross-Domain Mappings**: Links between automotive, railway, and industrial requirements
3. **AI-Enhanced Headings**: Meaningful titles for all standard clauses
4. **Navigable Documentation**: Professional HTML interface for browsing
5. **Integrated Examples**: Travelogue documents showing practical usage
6. **Semantic Relationships**: AI-discovered connections between standards

### Practical Applications

**For Safety Engineers**:
- Quick navigation between equivalent requirements across domains
- Understanding relationships between different safety standards
- Evidence for cross-domain safety argument transfer

**For Compliance Teams**:
- Gap analysis between different standard requirements
- Mapping existing processes to new standards
- Training material for multi-domain safety

**For Open Source Projects**:
- Understanding safety requirements without expensive standard purchases
- Building safety arguments using structural knowledge
- Contributing to collaborative safety knowledge base

### Advanced Usage

**Custom Standards Integration**:
```bash
# Add your own standard definitions
echo 'name="MY_STANDARD"' > ~/standards-atlas/data/MY_STANDARD
echo 'structure=("2024 1-r1.{1..50}")' >> ~/standards-atlas/data/MY_STANDARD
~/standards-atlas/tools/standards-atlas -d $(pwd)
```

**API Integration**:
```python
# Use doorstop programmatically
import doorstop
tree = doorstop.build()
for document in tree:
    for item in document:
        print(f"{item.uid}: {item.header}")
```

**Custom Relationships**:
```bash
# Create custom mapping file
echo -e "from=MY_STANDARD\nto=ISO26262\ntype=custom" > ~/standards-atlas/data/mapping05
echo "MY_STANDARD-001;Custom req;Maps to;ISO26262-6-007" >> ~/standards-atlas/data/mapping05
```

## Troubleshooting

### Common Issues

**AI Model Download Fails**:
```bash
# Manual model download
ramalama pull llama3.2:1b
# or use alternative model
~/standards-atlas/tools/intellidoc -g -l granite3-moe
```

**HTML Generation Errors**:
```bash
# Check doorstop installation
doorstop --version
# Ensure all requirements met
poetry install
```

**Missing Cross-References**:
```bash
# Verify mapping files exist
ls ~/standards-atlas/data/mapping*
# Re-run link processing
~/standards-atlas/tools/linkItems $(pwd)
```

### Performance Optimization

**For Large Datasets**:
- Process standards individually
- Use incremental updates (`-n` flag)
- Cache AI results between runs

**For Limited Resources**:
- Use smaller AI models (`llama3.2:1b`)
- Process in batch mode (`-b` flag)
- Limit concurrent operations

## Next Steps

### Explore Advanced Features

1. **Interactive AI Mode**: Try `~/standards-atlas/tools/intellidoc -i`
2. **Custom Mappings**: Create your own relationship definitions
3. **Integration**: Use with other requirements management tools
4. **Collaboration**: Share structural knowledge with team

### Learn More

- [Architecture Documentation](../architecture.md) - Understand system design
- [CLI Reference](../cli-reference.md) - Complete command documentation
- [Data Formats](../data-formats.md) - Structure definition syntax
- [Contributing Guide](../contributing.md) - Add your own standards

### Community Involvement

- Share your custom mappings and improvements
- Report issues and suggest enhancements
- Contribute standard structure definitions
- Help improve AI-generated content quality

---

**Congratulations!** You've successfully created a comprehensive, AI-enhanced, cross-domain safety standards reference. This foundation can be extended, customized, and shared to advance collaborative safety engineering.

*Total processing time: 2-3 hours*  
*Result: Professional multi-domain safety knowledge base*