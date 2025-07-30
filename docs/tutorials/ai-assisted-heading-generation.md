# AI-Assisted Heading Generation Tutorial

This tutorial focuses on using Standards Atlas's AI capabilities to generate meaningful headings for standard clauses. You'll learn to use different AI models, optimize processing workflows, and achieve high-quality results.

## Overview

Most safety standards have thousands of numbered clauses, but only a fraction have descriptive headings. Standards Atlas uses local AI models to generate meaningful 3-word headings that help navigate and understand standard content.

**What You'll Learn**:
- Model selection and configuration
- Processing modes and optimization
- Quality assessment and improvement
- Interactive vs. automated workflows

**Time Required**: 1-2 hours

## Background: The Heading Problem

### Before AI Enhancement
```
ISO 26262-6:2018 5.4.1    REQUIREMENT
ISO 26262-6:2018 5.4.2    REQUIREMENT  
ISO 26262-6:2018 5.4.3    REQUIREMENT
[... hundreds of similar entries ...]
```

### After AI Enhancement
```
ISO 26262-6:2018 5.4.1    Software Verification Methods
ISO 26262-6:2018 5.4.2    Test Case Design
ISO 26262-6:2018 5.4.3    Verification Evidence Documentation
[... meaningful headings throughout ...]
```

## Step 1: Model Selection and Setup

### 1.1 Understanding Available Models

| Model | Size | Speed | Quality | Best Use Case |
|-------|------|-------|---------|---------------|
| `llama3.2:1b` | 1GB | Very Fast | Good | Development, testing |
| `llama3.1` | 4GB | Fast | Good | General purpose |
| `nemotron` | 42GB | Slow | Excellent | Production quality |
| `granite3-moe` | 8GB | Medium | Good | Alternative option |

### 1.2 Test Your Setup

```bash
# Create test project
mkdir ~/ai-heading-test
cd ~/ai-heading-test

# Generate basic structure
~/standards-atlas/tools/standards-atlas -c -d $(pwd)

# Test basic AI functionality
~/standards-atlas/tools/intellidoc -g -l llama3.2:1b
```

**First Run Expectations**:
- Model download (automatic, one-time only)
- Server startup (30-60 seconds)
- Processing begins with progress indicators

### 1.3 Monitor Resource Usage

```bash
# In another terminal, monitor resources
htop
# or
top

# Watch for:
# - Memory usage (varies by model)
# - CPU utilization
# - Disk I/O for model loading
```

## Step 2: Development Workflow with Fast Models

### 2.1 Rapid Iteration Setup

```bash
# Use fastest model for development
MODEL="llama3.2:1b"

# Process small subset first
~/standards-atlas/tools/intellidoc -g -l $MODEL

# Check results quickly
~/standards-atlas/tools/standards-atlas -n -t -d $(pwd)
firefox requirements/index.html
```

### 2.2 Evaluate Initial Results

**Quality Assessment Criteria**:
1. **Relevance**: Does heading relate to clause content?
2. **Clarity**: Is the meaning understandable?
3. **Consistency**: Similar clauses get similar headings?
4. **Length**: Appropriate for 3-word limit?

**Example Evaluation**:
```
✓ Good: "Software Testing Methods"
✓ Good: "Safety Case Documentation"  
⚠ Okay: "Requirements Management Process"
✗ Poor: "Standard Compliance Text"
```

### 2.3 Iterative Improvement

```bash
# Process specific standard only
~/standards-atlas/tools/intellidoc -g -l llama3.2:1b -c csv/heading-data.csv

# Focus on specific clause types
# Edit CSV to filter only requirements (type 'r')
grep ";r$" csv/heading-data.csv > csv/requirements-only.csv
~/standards-atlas/tools/intellidoc -g -l llama3.2:1b -c csv/requirements-only.csv
```

## Step 3: Interactive Mode for Quality Control

### 3.1 Manual Selection Process

```bash
# Use interactive mode for careful selection
~/standards-atlas/tools/intellidoc -i -l llama3.1

# Interactive workflow:
# 1. System shows clause text
# 2. AI generates multiple heading options
# 3. You select the best option
# 4. Process continues to next clause
```

**Interactive Session Example**:
```
Missing heading for ISO26262-6:2018 5.4.1

Software verification shall be performed according to the verification 
strategy and the verification specification...

Generated options:
1. Software Verification Methods
2. Verification Strategy Implementation  
3. Software Testing Procedures
4. Verification Process Requirements

Make your choice: 1

✓ Selected: "Software Verification Methods"
```

### 3.2 Quality Control Strategies

**Best Practices for Interactive Mode**:
- Focus on high-visibility clauses first
- Use consistent terminology across related clauses  
- Consider domain-specific language
- Maintain parallel structure for similar requirements

**Keyboard Shortcuts**:
- Type number to select option
- Press Enter for first option
- Type "exit" to stop processing
- Type custom heading if none fit

### 3.3 Selective Processing

```bash
# Process only specific standards interactively
grep "ISO26262" csv/heading-data.csv > csv/automotive-only.csv
~/standards-atlas/tools/intellidoc -i -l llama3.1 -c csv/automotive-only.csv

# Or process by clause type
grep ";r;" csv/heading-data.csv > csv/requirements.csv
~/standards-atlas/tools/intellidoc -i -l llama3.1 -c csv/requirements.csv
```

## Step 4: Production Processing with High-Quality Models

### 4.1 Prepare for Long Processing

```bash
# Set up for production run
MODEL="nemotron"
OUTPUT_DIR="$(pwd)"

# Estimate processing time
CLAUSE_COUNT=$(wc -l < csv/heading-data.csv)
echo "Estimated time: $((CLAUSE_COUNT * 5 / 60)) minutes"

# Start processing (can take 1-2 hours)
~/standards-atlas/tools/intellidoc -g -l $MODEL 2>&1 | tee ai-processing.log
```

### 4.2 Monitor Long-Running Process

```bash
# In another terminal, monitor progress
tail -f Tokenizer.log

# Watch for processing patterns
grep "generate headings" Tokenizer.log | tail -10

# Check server status
ps aux | grep ramalama
```

### 4.3 Handle Interruptions

```bash
# If process is interrupted, it can be resumed
# AI results are cached, so completed clauses are skipped
~/standards-atlas/tools/intellidoc -g -l nemotron

# Force regeneration if needed
rm -rf cache_files/  # (if exists)
~/standards-atlas/tools/intellidoc -g -l nemotron
```

## Step 5: Bulk Processing and Automation

### 5.1 Automated Bulk Mode

```bash
# Process everything automatically
~/standards-atlas/tools/intellidoc -b -l nemotron

# Bulk mode:
# - No user interaction required
# - Selects best heading automatically
# - Suitable for overnight processing
# - Logs all decisions
```

### 5.2 Batch Processing by Domain

```bash
# Process each domain separately
DOMAINS=("automotive" "railway" "industrial")

for domain in "${DOMAINS[@]}"; do
    echo "Processing $domain standards..."
    grep -i "$domain" csv/heading-data.csv > "csv/${domain}.csv"
    ~/standards-atlas/tools/intellidoc -b -l nemotron -c "csv/${domain}.csv"
done
```

### 5.3 Quality Validation

```bash
# Generate reports on heading quality
python3 << 'EOF'
import csv
import re

def analyze_headings(filename):
    word_counts = []
    with open(filename, 'r') as f:
        reader = csv.reader(f, delimiter=';')
        for row in reader:
            if len(row) >= 4:
                heading = row[3]
                words = len(heading.split())
                word_counts.append(words)
    
    print(f"Heading analysis for {filename}:")
    print(f"Average words: {sum(word_counts)/len(word_counts):.1f}")
    print(f"3-word headings: {word_counts.count(3)}/{len(word_counts)}")
    print(f"Range: {min(word_counts)}-{max(word_counts)} words")

analyze_headings('csv/heading-data.csv')
EOF
```

## Step 6: Advanced Techniques

### 6.1 Custom Prompt Engineering

For advanced users, modify prompts in the source code:

```python
# In tools/IntelliDoc/HeadingFactory.py
# Customize prompts for specific domains

automotive_prompt = f"create a max 3 word automotive safety heading for: {text}"
railway_prompt = f"create a max 3 word railway safety heading for: {text}"
industrial_prompt = f"create a max 3 word industrial safety heading for: {text}"
```

### 6.2 Multi-Model Comparison

```bash
# Generate headings with different models
for model in llama3.1 nemotron granite3-moe; do
    echo "Processing with $model..."
    ~/standards-atlas/tools/intellidoc -g -l $model
    mv csv/heading-data.csv "csv/headings-${model}.csv"
done

# Compare results
python3 << 'EOF'
import csv

def compare_models():
    models = ['llama3.1', 'nemotron', 'granite3-moe']
    results = {}
    
    for model in models:
        results[model] = {}
        with open(f'csv/headings-{model}.csv', 'r') as f:
            reader = csv.reader(f, delimiter=';')
            for row in reader:
                if len(row) >= 4:
                    clause_id = row[2]
                    heading = row[3]
                    results[model][clause_id] = heading
    
    # Find differences
    common_clauses = set(results['llama3.1'].keys())
    for model in models[1:]:
        common_clauses &= set(results[model].keys())
    
    print("Model comparison for common clauses:")
    for clause in list(common_clauses)[:5]:  # Show first 5
        print(f"\nClause: {clause}")
        for model in models:
            print(f"  {model}: {results[model][clause]}")

compare_models()
EOF
```

### 6.3 Domain-Specific Processing

```bash
# Create domain-specific workflows
create_domain_workflow() {
    local domain=$1
    local model=$2
    
    echo "Creating $domain-specific headings with $model..."
    
    # Filter for domain-specific clauses
    grep -i "$domain" csv/heading-data.csv > "csv/${domain}-clauses.csv"
    
    # Process with appropriate model
    ~/standards-atlas/tools/intellidoc -g -l $model -c "csv/${domain}-clauses.csv"
    
    # Generate domain-specific output
    ~/standards-atlas/tools/standards-atlas -n -t -d "${domain}-output"
}

# Usage examples
create_domain_workflow "automotive" "nemotron"
create_domain_workflow "railway" "granite3-moe"
```

## Step 7: Quality Assurance and Validation

### 7.1 Automated Quality Checks

```bash
# Check for common quality issues
python3 << 'EOF'
import csv
import re

def quality_check(filename):
    issues = []
    
    with open(filename, 'r') as f:
        reader = csv.reader(f, delimiter=';')
        for i, row in enumerate(reader):
            if len(row) < 4:
                continue
                
            clause_id = row[2]
            heading = row[3]
            
            # Check for generic headings
            if heading.upper() in ['REQUIREMENT', 'CLAUSE', 'TOC']:
                issues.append(f"Line {i}: Generic heading '{heading}' for {clause_id}")
            
            # Check word count
            words = len(heading.split())
            if words > 5:
                issues.append(f"Line {i}: Too long '{heading}' ({words} words)")
            
            # Check for weird patterns
            if re.search(r'\d{4}', heading):  # Years in headings
                issues.append(f"Line {i}: Contains year '{heading}'")
    
    print(f"Quality issues found: {len(issues)}")
    for issue in issues[:10]:  # Show first 10
        print(f"  {issue}")

quality_check('csv/heading-data.csv')
EOF
```

### 7.2 Manual Review Process

```bash
# Create review-friendly format
python3 << 'EOF'
import csv

with open('csv/heading-data.csv', 'r') as infile:
    with open('headings-review.txt', 'w') as outfile:
        reader = csv.reader(infile, delimiter=';')
        for row in reader:
            if len(row) >= 4:
                clause_id = row[2]
                heading = row[3]
                clause_type = row[4]
                outfile.write(f"{clause_id:40} | {heading:30} | {clause_type}\n")

print("Review file created: headings-review.txt")
EOF

# Review with text editor
nano headings-review.txt
# or
code headings-review.txt
```

### 7.3 Statistical Analysis

```bash
# Generate comprehensive statistics
python3 << 'EOF'
import csv
from collections import defaultdict, Counter

def analyze_results(filename):
    headings_by_type = defaultdict(list)
    word_usage = Counter()
    
    with open(filename, 'r') as f:
        reader = csv.reader(f, delimiter=';')
        for row in reader:
            if len(row) >= 4:
                heading = row[3]
                clause_type = row[4] if len(row) > 4 else 'unknown'
                
                headings_by_type[clause_type].append(heading)
                
                # Count word usage
                words = heading.lower().split()
                word_usage.update(words)
    
    print("=== Heading Analysis ===")
    print(f"Total headings: {sum(len(h) for h in headings_by_type.values())}")
    
    print("\n=== By Clause Type ===")
    for clause_type, headings in headings_by_type.items():
        print(f"{clause_type}: {len(headings)} headings")
    
    print("\n=== Most Common Words ===")
    for word, count in word_usage.most_common(10):
        print(f"{word}: {count}")
    
    print("\n=== Sample Headings by Type ===")
    for clause_type, headings in headings_by_type.items():
        if headings:
            print(f"\n{clause_type}:")
            for heading in headings[:3]:  # Show first 3
                print(f"  - {heading}")

analyze_results('csv/heading-data.csv')
EOF
```

## Step 8: Integration and Final Output

### 8.1 Apply Generated Headings

```bash
# Integrate AI-generated headings into structure
~/standards-atlas/tools/standards-atlas -n -t -d $(pwd)

# Verify results
firefox requirements/index.html
```

### 8.2 Export for External Use

```bash
# Export headings for other tools
python3 << 'EOF'
import csv
import json

headings = {}
with open('csv/heading-data.csv', 'r') as f:
    reader = csv.reader(f, delimiter=';')
    for row in reader:
        if len(row) >= 4:
            clause_id = row[2]
            heading = row[3]
            headings[clause_id] = heading

# JSON export
with open('ai-headings.json', 'w') as f:
    json.dump(headings, f, indent=2)

# Simple text export
with open('ai-headings.txt', 'w') as f:
    for clause_id, heading in sorted(headings.items()):
        f.write(f"{clause_id}: {heading}\n")

print("Exports created: ai-headings.json, ai-headings.txt")
EOF
```

### 8.3 Create Summary Report

```bash
# Generate processing summary
cat << 'EOF' > ai-processing-summary.md
# AI Heading Generation Summary

## Processing Details
- **Model Used**: nemotron
- **Processing Time**: $(date)
- **Clauses Processed**: $(wc -l < csv/heading-data.csv)
- **Success Rate**: $(grep -v "REQUIREMENT\|CLAUSE\|TOC" csv/heading-data.csv | wc -l)/$(wc -l < csv/heading-data.csv)

## Quality Metrics
- Average heading length: $(python3 -c "import csv; data=[len(row[3].split()) for row in csv.reader(open('csv/heading-data.csv')) if len(row)>=4]; print(f'{sum(data)/len(data):.1f} words')")
- Standards coverage: Complete
- Cross-reference integrity: Verified

## Next Steps
- Manual review of generated headings
- Integration with document references
- Publication of enhanced structure
EOF

echo "Summary report created: ai-processing-summary.md"
```

## Troubleshooting AI Issues

### Common Problems

**Model Download Failures**:
```bash
# Manual model management
ramalama list  # Show available models
ramalama pull llama3.2:1b  # Manual download
ramalama remove old-model  # Clean up space
```

**Memory Issues**:
```bash
# Use smaller model
~/standards-atlas/tools/intellidoc -g -l llama3.2:1b

# Monitor memory usage
free -h
# If needed, add swap space or use cloud processing
```

**Quality Issues**:
- Try different models for comparison
- Use interactive mode for important clauses
- Customize prompts for specific domains
- Post-process results with custom scripts

**Performance Optimization**:
```bash
# Process incrementally
split -l 100 csv/heading-data.csv csv/chunk-
for chunk in csv/chunk-*; do
    ~/standards-atlas/tools/intellidoc -g -l nemotron -c $chunk
done
```

## Best Practices Summary

### Model Selection Strategy
1. **Development**: Use `llama3.2:1b` for rapid iteration
2. **Quality Control**: Use `llama3.1` for interactive review
3. **Production**: Use `nemotron` for final high-quality results
4. **Comparison**: Test multiple models for optimal results

### Processing Workflow
1. Start with basic structure generation
2. Test AI setup with fast model
3. Use interactive mode for critical clauses
4. Run bulk processing for complete coverage
5. Validate and review results
6. Integrate into final documentation

### Quality Assurance
- Set realistic expectations (80-90% good headings)
- Focus manual review on high-impact clauses
- Use consistent terminology across related standards
- Validate results before final publication

---

**Result**: You now have meaningful, AI-generated headings that transform generic clause labels into navigable, understandable documentation. This significantly improves the usability of standards structures and enables better cross-domain understanding.

*This process transforms thousands of generic "REQUIREMENT" labels into meaningful navigation aids, making safety standards much more accessible and usable.*