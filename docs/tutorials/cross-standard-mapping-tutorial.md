# Cross-Standard Mapping Tutorial

This tutorial teaches you how to create and use cross-standard relationships in Standards Atlas. You'll learn to map equivalent requirements between different safety domains and create navigable connections across automotive, railway, and industrial standards.

## Overview

Safety standards often address similar concepts but use different terminology and structure. Cross-standard mapping enables:

- **Knowledge Transfer**: Apply automotive safety expertise to railway projects
- **Gap Analysis**: Identify missing coverage when transitioning between standards
- **Harmonization**: Understand relationships between related requirements
- **Training**: Learn one standard by comparing to a familiar one

**Time Required**: 1-2 hours  
**Difficulty**: Intermediate

## Background: Why Cross-Standard Mapping Matters

### The Multi-Domain Challenge

Modern safety engineers often work across multiple domains:

```
Automotive Engineer → Railway Project
- Knows ISO 26262 well
- Needs to understand EN 50129
- Question: Which railway clauses match automotive requirements?

Industrial Engineer → Automotive Project  
- Expert in IEC 61508
- Must learn ISO 26262
- Question: How do automotive requirements relate to industrial ones?
```

### Standards Atlas Solution

```
ISO 26262-6:2018 5.4.1 "Software Verification Methods"
         ↕ (mapped to)
IEC 61508-3:2010 7.4.2 "Software Verification and Testing"
         ↕ (mapped to)  
EN 50129:2003 4.3.2.1 "Software Testing Requirements"
```

## Step 1: Understanding Existing Mappings

### 1.1 Explore Pre-Defined Relationships

```bash
# Create test project
mkdir ~/mapping-tutorial
cd ~/mapping-tutorial

# Generate structure with existing mappings
~/standards-atlas/tools/standards-atlas -t -d $(pwd)
~/standards-atlas/tools/linkItems $(pwd)
~/standards-atlas/tools/standards-atlas -n -t -d $(pwd)

# Browse results
firefox requirements/index.html
```

### 1.2 Examine Mapping Files

```bash
# Look at existing mapping definitions
ls ~/standards-atlas/data/mapping*

# Examine mapping structure
head -20 ~/standards-atlas/data/mapping01
```

**Mapping File Format**:
```bash
# Header defines relationship
from=ISO26262
to=IEC61508
type=equivalence

# Data defines specific clause relationships
ISO26262-6-007;Software verification;Verification methods;IEC61508-3-047
ISO26262-6-008;Software testing;Testing procedures;IEC61508-3-048
[fromUID];[context];[description];[toUID]
```

### 1.3 Navigate Cross-References

**Exploration Exercise**:
1. Open ISO 26262 Part 6 (Software)
2. Find clause 5.4.1 (Software verification)
3. Look for links to IEC 61508
4. Follow link to see industrial equivalent
5. Check for railway connections

## Step 2: Creating Custom Mappings

### 2.1 Identify Mapping Opportunities

```bash
# Generate CSV data for analysis
~/standards-atlas/tools/standards-atlas -c -d $(pwd)

# Examine structure to find mapping candidates
head -50 csv/heading-data.csv
```

**Look for Similar Concepts**:
- Software verification/testing procedures
- Safety case documentation requirements  
- Configuration management processes
- Tool qualification requirements

### 2.2 Create Custom Mapping File

```bash
# Create new mapping file
cat > ~/standards-atlas/data/mapping05 << 'EOF'
# Custom mapping: Railway to Automotive
from=EN50129
to=ISO26262
type=similarity

# Software testing relationships
EN50129-003;Software testing;Testing procedures;ISO26262-6-007
EN50129-004;Test documentation;Test evidence;ISO26262-6-008
EN50129-005;Verification methods;Verification strategy;ISO26262-6-009

# Safety case relationships  
EN50129-010;Safety case;Safety argument;ISO26262-10-005
EN50129-011;Hazard analysis;Hazard identification;ISO26262-3-007

# Configuration management
EN50129-020;Configuration control;Change management;ISO26262-8-012
EN50129-021;Version control;Document control;ISO26262-8-013
EOF
```

### 2.3 Apply Custom Mappings

```bash
# Process new mappings
~/standards-atlas/tools/linkItems $(pwd)

# Regenerate documentation
~/standards-atlas/tools/standards-atlas -n -t -d $(pwd)

# Verify new relationships
firefox requirements/index.html
```

## Step 3: Advanced Mapping Techniques

### 3.1 Many-to-Many Relationships

Some concepts span multiple clauses:

```bash
# Create complex mapping
cat > ~/standards-atlas/data/mapping06 << 'EOF'
# Complex relationships: Tool Qualification
from=ISO26262
to=IEC61508
type=equivalence

# Tool qualification concept maps to multiple clauses
ISO26262-8-011;Tool qualification;Tool assessment;IEC61508-3-035
ISO26262-8-011;Tool qualification;Tool validation;IEC61508-3-036
ISO26262-8-011;Tool qualification;Tool verification;IEC61508-3-037

# Conversely, multiple ISO clauses map to one IEC clause
ISO26262-6-025;Unit testing;Software testing;IEC61508-3-047
ISO26262-6-026;Integration testing;Software testing;IEC61508-3-047
ISO26262-6-027;System testing;Software testing;IEC61508-3-047
EOF
```

### 3.2 Hierarchical Relationships

Map parent-child relationships across standards:

```bash
# Create hierarchical mapping
cat > ~/standards-atlas/data/mapping07 << 'EOF'
# Hierarchical mapping: Safety Lifecycle
from=ISO26262
to=IEC61508
type=hierarchy

# Top-level lifecycle mapping
ISO26262-2-005;Safety lifecycle;Overall lifecycle;IEC61508-1-006

# Detailed phase mappings (children)
ISO26262-2-006;Concept phase;Concept definition;IEC61508-2-007
ISO26262-2-007;Product development;System development;IEC61508-2-008
ISO26262-2-008;Production phase;Realization phase;IEC61508-2-009
ISO26262-2-009;Operation phase;Operation/maintenance;IEC61508-2-010
EOF
```

### 3.3 Conditional Relationships

Some relationships depend on context:

```bash
# Create conditional mapping
cat > ~/standards-atlas/data/mapping08 << 'EOF'
# Conditional mapping: ASIL to SIL
from=ISO26262
to=IEC61508  
type=conditional

# ASIL levels map differently to SIL levels
ISO26262-3-008;ASIL A;Low risk;IEC61508-1-015  # SIL 1
ISO26262-3-009;ASIL B;Medium risk;IEC61508-1-016  # SIL 2
ISO26262-3-010;ASIL C;High risk;IEC61508-1-017  # SIL 3
ISO26262-3-011;ASIL D;Very high risk;IEC61508-1-018  # SIL 4
EOF
```

## Step 4: Quality Assurance for Mappings

### 4.1 Validate Mapping Consistency

```bash
# Check for broken mappings
python3 << 'EOF'
import csv
import os

def validate_mappings():
    # Load all clause IDs from structure
    valid_ids = set()
    with open('csv/uid-ref-map.csv', 'r') as f:
        reader = csv.reader(f, delimiter=';')
        for row in reader:
            if len(row) >= 2:
                valid_ids.add(row[1])
    
    # Check each mapping file
    mapping_dir = os.path.expanduser('~/standards-atlas/data')
    for filename in os.listdir(mapping_dir):
        if filename.startswith('mapping'):
            filepath = os.path.join(mapping_dir, filename)
            print(f"\nValidating {filename}:")
            
            with open(filepath, 'r') as f:
                lines = f.readlines()
                
            for i, line in enumerate(lines):
                if ';' in line and not line.startswith('#'):
                    parts = line.strip().split(';')
                    if len(parts) >= 4:
                        from_id = parts[0]
                        to_id = parts[3]
                        
                        if from_id not in valid_ids:
                            print(f"  Line {i+1}: Invalid FROM ID: {from_id}")
                        if to_id not in valid_ids:
                            print(f"  Line {i+1}: Invalid TO ID: {to_id}")

validate_mappings()
EOF
```

### 4.2 Check Bidirectionality

```bash
# Verify bidirectional relationships
python3 << 'EOF'
import csv
import os
from collections import defaultdict

def check_bidirectionality():
    relationships = defaultdict(set)
    
    # Load all relationships
    mapping_dir = os.path.expanduser('~/standards-atlas/data')
    for filename in os.listdir(mapping_dir):
        if filename.startswith('mapping'):
            filepath = os.path.join(mapping_dir, filename)
            
            with open(filepath, 'r') as f:
                lines = f.readlines()
                
            for line in lines:
                if ';' in line and not line.startswith('#'):
                    parts = line.strip().split(';')
                    if len(parts) >= 4:
                        from_id = parts[0]
                        to_id = parts[3]
                        relationships[from_id].add(to_id)
    
    # Check for missing reverse relationships
    print("Checking bidirectionality:")
    for from_id, to_ids in relationships.items():
        for to_id in to_ids:
            if from_id not in relationships.get(to_id, set()):
                print(f"Missing reverse: {to_id} -> {from_id}")

check_bidirectionality()
EOF
```

### 4.3 Coverage Analysis

```bash
# Analyze mapping coverage
python3 << 'EOF'
import csv
from collections import defaultdict

def analyze_coverage():
    # Load all clauses by standard
    clauses_by_standard = defaultdict(set)
    with open('csv/uid-ref-map.csv', 'r') as f:
        reader = csv.reader(f, delimiter=';')
        for row in reader:
            if len(row) >= 3:
                uid = row[1]
                clause_id = row[2]
                standard = uid.split('-')[0]
                clauses_by_standard[standard].add(uid)
    
    # Load mapped clauses
    mapped_clauses = set()
    mapping_dir = os.path.expanduser('~/standards-atlas/data')
    for filename in os.listdir(mapping_dir):
        if filename.startswith('mapping'):
            filepath = os.path.join(mapping_dir, filename)
            
            with open(filepath, 'r') as f:
                lines = f.readlines()
                
            for line in lines:
                if ';' in line and not line.startswith('#'):
                    parts = line.strip().split(';')
                    if len(parts) >= 4:
                        mapped_clauses.add(parts[0])
                        mapped_clauses.add(parts[3])
    
    # Calculate coverage
    print("Mapping coverage by standard:")
    for standard, clauses in clauses_by_standard.items():
        mapped = len([c for c in clauses if c in mapped_clauses])
        total = len(clauses)
        coverage = (mapped / total * 100) if total > 0 else 0
        print(f"  {standard}: {mapped}/{total} ({coverage:.1f}%)")

analyze_coverage()
EOF
```

## Step 5: Semantic Relationship Discovery

### 5.1 AI-Assisted Mapping

Use AI to suggest potential relationships:

```bash
# Generate AI headings first (if not done)
~/standards-atlas/tools/intellidoc -g -l nemotron

# Process semantic relationships
~/standards-atlas/tools/relator $(pwd) $(pwd)/csv/uid-ref-map.csv

# This creates additional relationship suggestions
# based on AI analysis of clause content
```

### 5.2 Review AI Suggestions

```bash
# Examine AI-generated relationships
head -50 data/relations.csv

# Format: from_clause;to_clause;similarity_score
# Higher scores indicate stronger relationships
```

### 5.3 Convert AI Suggestions to Mappings

```bash
# Create mapping from high-confidence AI relationships
python3 << 'EOF'
import csv

def ai_to_mapping():
    high_confidence = []
    
    # Load AI relationships
    with open('data/relations.csv', 'r') as f:
        reader = csv.reader(f, delimiter=';')
        for row in reader:
            if len(row) >= 3:
                from_clause = row[0]
                to_clause = row[1]
                score = float(row[2])
                
                # Only high-confidence relationships
                if score > 0.8:
                    high_confidence.append((from_clause, to_clause, score))
    
    # Group by standard pairs
    standard_pairs = {}
    for from_clause, to_clause, score in high_confidence:
        from_std = from_clause.split('-')[0]
        to_std = to_clause.split('-')[0]
        
        if from_std != to_std:  # Cross-standard only
            pair = f"{from_std}-{to_std}"
            if pair not in standard_pairs:
                standard_pairs[pair] = []
            standard_pairs[pair].append((from_clause, to_clause, score))
    
    # Create mapping files
    for pair, relationships in standard_pairs.items():
        from_std, to_std = pair.split('-')
        filename = f"~/standards-atlas/data/mapping-ai-{pair.lower()}"
        
        with open(filename, 'w') as f:
            f.write(f"# AI-generated mapping: {from_std} to {to_std}\n")
            f.write(f"from={from_std}\n")
            f.write(f"to={to_std}\n")
            f.write(f"type=similarity\n\n")
            
            for from_clause, to_clause, score in relationships[:20]:  # Top 20
                f.write(f"{from_clause};AI relationship;Similarity {score:.2f};{to_clause}\n")
        
        print(f"Created {filename} with {len(relationships[:20])} relationships")

ai_to_mapping()
EOF
```

## Step 6: Advanced Mapping Applications

### 6.1 Gap Analysis Workflow

```bash
# Create gap analysis mapping
python3 << 'EOF'
import csv
from collections import defaultdict

def gap_analysis():
    # Load existing mappings
    mapped_from = set()
    mapped_to = set()
    
    mapping_dir = os.path.expanduser('~/standards-atlas/data')
    for filename in os.listdir(mapping_dir):
        if filename.startswith('mapping'):
            filepath = os.path.join(mapping_dir, filename)
            
            with open(filepath, 'r') as f:
                lines = f.readlines()
                
            for line in lines:
                if ';' in line and not line.startswith('#'):
                    parts = line.strip().split(';')
                    if len(parts) >= 4:
                        mapped_from.add(parts[0])
                        mapped_to.add(parts[3])
    
    # Load all clauses
    all_clauses = defaultdict(set)
    with open('csv/uid-ref-map.csv', 'r') as f:
        reader = csv.reader(f, delimiter=';')
        for row in reader:
            if len(row) >= 3:
                uid = row[1]
                standard = uid.split('-')[0]
                all_clauses[standard].add(uid)
    
    # Find unmapped clauses
    print("Gap Analysis - Unmapped Clauses:")
    for standard, clauses in all_clauses.items():
        unmapped = clauses - mapped_from - mapped_to
        if unmapped:
            print(f"\n{standard} ({len(unmapped)} unmapped):")
            for clause in sorted(list(unmapped))[:5]:  # Show first 5
                print(f"  {clause}")

gap_analysis()
EOF
```

### 6.2 Domain Transfer Workflows

Create specialized mappings for domain transitions:

```bash
# Automotive → Railway transfer
cat > ~/standards-atlas/data/mapping-auto-rail << 'EOF'
# Domain transfer: Automotive to Railway
from=ISO26262
to=EN50129
type=domain_transfer

# Key concept translations
ISO26262-3-007;ASIL classification;Risk assessment;EN50129-005
ISO26262-4-008;Safety requirements;Safety functions;EN50129-010
ISO26262-6-007;Software verification;Software testing;EN50129-015
ISO26262-10-005;Safety case;Safety demonstration;EN50129-020
EOF

# Industrial → Automotive transfer  
cat > ~/standards-atlas/data/mapping-ind-auto << 'EOF'
# Domain transfer: Industrial to Automotive
from=IEC61508
to=ISO26262
type=domain_transfer

# Lifecycle translation
IEC61508-1-006;Safety lifecycle;Item development;ISO26262-2-005
IEC61508-2-007;Hazard analysis;Hazard analysis;ISO26262-3-007
IEC61508-3-047;Software testing;Software verification;ISO26262-6-007
IEC61508-4-005;Safety case;Safety case;ISO26262-10-005
EOF
```

### 6.3 Training and Education Mappings

```bash
# Create learning pathway mappings
cat > ~/standards-atlas/data/mapping-learning << 'EOF'
# Learning pathway: IEC 61508 basics for ISO 26262 experts
from=ISO26262
to=IEC61508
type=learning

# Familiar automotive concepts → Industrial equivalents
ISO26262-1-004;Functional safety;Functional safety;IEC61508-1-004
ISO26262-2-005;Safety lifecycle;Safety lifecycle;IEC61508-1-006
ISO26262-3-007;Hazard analysis;Hazard analysis;IEC61508-2-007
ISO26262-4-008;Safety requirements;Safety functions;IEC61508-2-010
ISO26262-6-007;Software verification;Software verification;IEC61508-3-047
EOF
```

## Step 7: Visualization and Analysis

### 7.1 Generate Relationship Reports

```bash
# Create comprehensive relationship report
python3 << 'EOF'
import csv
import os
from collections import defaultdict

def generate_report():
    relationships = defaultdict(list)
    
    # Load all mappings
    mapping_dir = os.path.expanduser('~/standards-atlas/data')
    for filename in os.listdir(mapping_dir):
        if filename.startswith('mapping'):
            filepath = os.path.join(mapping_dir, filename)
            
            # Read header
            mapping_type = "unknown"
            from_std = "unknown"
            to_std = "unknown"
            
            with open(filepath, 'r') as f:
                lines = f.readlines()
                
            for line in lines:
                line = line.strip()
                if line.startswith('from='):
                    from_std = line.split('=')[1]
                elif line.startswith('to='):
                    to_std = line.split('=')[1]
                elif line.startswith('type='):
                    mapping_type = line.split('=')[1]
                elif ';' in line and not line.startswith('#'):
                    parts = line.split(';')
                    if len(parts) >= 4:
                        relationships[f"{from_std}→{to_std}"].append({
                            'from': parts[0],
                            'to': parts[3],
                            'description': parts[2],
                            'type': mapping_type
                        })
    
    # Generate report
    with open('relationship-report.md', 'w') as f:
        f.write("# Cross-Standard Relationship Report\n\n")
        
        for pair, rels in relationships.items():
            f.write(f"## {pair}\n")
            f.write(f"- **Count**: {len(rels)} relationships\n")
            f.write(f"- **Type**: {rels[0]['type'] if rels else 'unknown'}\n\n")
            
            f.write("### Sample Relationships\n")
            for rel in rels[:5]:  # Show first 5
                f.write(f"- `{rel['from']}` → `{rel['to']}`: {rel['description']}\n")
            f.write("\n")
    
    print("Report generated: relationship-report.md")

generate_report()
EOF
```

### 7.2 Create Navigation Aids

```bash
# Generate cross-reference index
python3 << 'EOF'
import csv
import os
from collections import defaultdict

def create_index():
    # Create bidirectional index
    index = defaultdict(lambda: defaultdict(list))
    
    # Load mappings
    mapping_dir = os.path.expanduser('~/standards-atlas/data')
    for filename in os.listdir(mapping_dir):
        if filename.startswith('mapping'):
            filepath = os.path.join(mapping_dir, filename)
            
            with open(filepath, 'r') as f:
                lines = f.readlines()
                
            for line in lines:
                if ';' in line and not line.startswith('#'):
                    parts = line.strip().split(';')
                    if len(parts) >= 4:
                        from_clause = parts[0]
                        to_clause = parts[3]
                        description = parts[2]
                        
                        # Add both directions
                        index[from_clause]['related'].append((to_clause, description))
                        index[to_clause]['related'].append((from_clause, description))
    
    # Write index
    with open('cross-reference-index.txt', 'w') as f:
        for clause in sorted(index.keys()):
            if index[clause]['related']:
                f.write(f"{clause}:\n")
                for related, desc in index[clause]['related']:
                    f.write(f"  → {related}: {desc}\n")
                f.write("\n")
    
    print("Index created: cross-reference-index.txt")

create_index()
EOF
```

## Step 8: Maintenance and Updates

### 8.1 Mapping Maintenance Workflow

```bash
# Create maintenance script
cat > maintain-mappings.sh << 'EOF'
#!/bin/bash

# Standards Atlas Mapping Maintenance

echo "=== Mapping Maintenance Report ==="
echo "Date: $(date)"
echo

# Check for broken mappings
echo "Checking for broken references..."
python3 -c "
import csv, os
valid_ids = set()
with open('csv/uid-ref-map.csv', 'r') as f:
    reader = csv.reader(f, delimiter=';')
    for row in reader:
        if len(row) >= 2:
            valid_ids.add(row[1])

mapping_dir = os.path.expanduser('~/standards-atlas/data')
broken_count = 0
for filename in os.listdir(mapping_dir):
    if filename.startswith('mapping'):
        with open(os.path.join(mapping_dir, filename), 'r') as f:
            for i, line in enumerate(f):
                if ';' in line and not line.startswith('#'):
                    parts = line.strip().split(';')
                    if len(parts) >= 4:
                        if parts[0] not in valid_ids or parts[3] not in valid_ids:
                            print(f'BROKEN: {filename}:{i+1} {parts[0]} -> {parts[3]}')
                            broken_count += 1
print(f'Total broken references: {broken_count}')
"

# Count total relationships
echo
echo "Relationship summary:"
wc -l ~/standards-atlas/data/mapping* | tail -1

# Apply all mappings
echo
echo "Applying mappings..."
~/standards-atlas/tools/linkItems $(pwd)

echo "Maintenance complete."
EOF

chmod +x maintain-mappings.sh
```

### 8.2 Version Control for Mappings

```bash
# Initialize mapping version control
cd ~/standards-atlas/data
git init
git add mapping*
git commit -m "Initial mapping definitions"

# Create development branch for experimental mappings
git checkout -b experimental-mappings

# Work on new mappings...
# When ready, merge back to main
git checkout main
git merge experimental-mappings
```

### 8.3 Collaborative Mapping

```bash
# Export mappings for sharing
tar -czf my-mappings-$(date +%Y%m%d).tar.gz ~/standards-atlas/data/mapping*

# Import mappings from others
# tar -xzf shared-mappings.tar.gz -C ~/standards-atlas/data/

# Validate imported mappings
./maintain-mappings.sh
```

## Results and Applications

### What You've Accomplished

After completing this tutorial, you can:

1. **Navigate Cross-Domain**: Move between automotive, railway, and industrial standards
2. **Create Custom Mappings**: Define relationships specific to your needs
3. **Quality Assurance**: Validate and maintain mapping integrity
4. **Gap Analysis**: Identify unmapped areas requiring attention
5. **Collaboration**: Share and merge mapping definitions

### Practical Applications

**For Multi-Domain Engineers**:
- Rapid learning of new standards through familiar concepts
- Evidence for cross-domain safety argument transfer
- Standardized approach to domain transition

**For Training Organizations**:
- Teaching pathways from known to unknown standards
- Comparative analysis exercises
- Cross-domain competency development

**For Consulting**:
- Systematic approach to standard migration projects
- Quality assurance for cross-domain compliance
- Standardized mapping methodologies

### Advanced Applications

**Research and Development**:
- Quantitative analysis of standard relationships
- Machine learning training data for automatic mapping
- Standards harmonization research

**Tool Integration**:
- Export mappings to other requirements tools
- Integration with compliance management systems
- Custom analysis and reporting tools

---

**Congratulations!** You now understand how to create, maintain, and use cross-standard mappings effectively. This capability transforms Standards Atlas from a simple structure browser into a powerful cross-domain knowledge navigation system.

*This skill enables safety engineers to leverage their existing knowledge across multiple domains, accelerating learning and improving cross-domain safety engineering.*