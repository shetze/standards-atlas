# Troubleshooting Guide

This guide helps you diagnose and fix common issues with Standards Atlas. Issues are organized by component and severity.

## Quick Diagnostics

### System Health Check

Run this comprehensive check first:

```bash
# Basic system check
echo "=== Standards Atlas Health Check ==="
echo "Date: $(date)"
echo

# Check Python environment
echo "Python version:"
python3 --version || echo "❌ Python 3 not found"

# Check Poetry
echo "Poetry version:"
poetry --version || echo "❌ Poetry not found"

# Check virtual environment
if [[ "$VIRTUAL_ENV" ]]; then
    echo "✓ Virtual environment active: $VIRTUAL_ENV"
else
    echo "⚠️  No virtual environment detected"
fi

# Check doorstop
echo "Doorstop version:"
doorstop --version || echo "❌ Doorstop not found"

# Check RamaLama
echo "RamaLama status:"
which ramalama && ramalama --version || echo "❌ RamaLama not found"

# Check Standards Atlas tools
echo "Standards Atlas tools:"
for tool in standards-atlas intellidoc linkItems referenceItems; do
    if [[ -x "tools/$tool" ]]; then
        echo "✓ $tool"
    else
        echo "❌ $tool not found or not executable"
    fi
done

# Check data directory
if [[ -d "data" ]]; then
    echo "✓ Data directory exists ($(ls data | wc -l) files)"
else
    echo "❌ Data directory not found"
fi
```

### Component Status

```bash
# Check individual components
echo "=== Component Status ==="

# Test doorstop
doorstop --help > /dev/null && echo "✓ Doorstop working" || echo "❌ Doorstop issues"

# Test RamaLama (basic)
timeout 30 python3 -c "from tools.IntelliDoc.RamalamaClient import RamaLama; print('✓ RamaLama import successful')" 2>/dev/null || echo "❌ RamaLama import failed"

# Test Standards Atlas
./tools/standards-atlas --help > /dev/null && echo "✓ standards-atlas working" || echo "❌ standards-atlas issues"
```

## Installation Issues

### Python Environment Problems

**Issue**: `ModuleNotFoundError` or `ImportError`

```bash
# Symptoms
python3 -c "import doorstop"
# ModuleNotFoundError: No module named 'doorstop'

# Solution 1: Reinstall dependencies
poetry install

# Solution 2: Check virtual environment
poetry shell
poetry install

# Solution 3: Manual dependency check
poetry show | grep doorstop
poetry add doorstop@3.0.2

# Solution 4: Clean reinstall
rm -rf .venv
poetry install
source .venv/bin/activate
```

**Issue**: Poetry not found or not working

```bash
# Install Poetry
curl -sSL https://install.python-poetry.org | python3 -

# Add to PATH
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# Verify installation
poetry --version
```

**Issue**: Wrong Python version

```bash
# Check Python version
python3 --version
# Should be 3.10 or higher

# If too old, install newer Python
# Ubuntu/Debian:
sudo apt update
sudo apt install python3.11 python3.11-venv python3.11-pip

# Update poetry configuration
poetry config python-version 3.11
poetry install
```

### Doorstop Patch Issues

**Issue**: Doorstop patch failed during setup

```bash
# Check if patch was applied
ls ~/.local/lib/python*/site-packages/doorstop/.doorstop_custom_patch_applied

# If missing, manually apply patch
./cfg/patch-doorstop

# If patch conflicts, check doorstop version
doorstop --version
# Expected: 3.0.2

# If wrong version, reinstall
poetry remove doorstop
poetry add doorstop@3.0.2
./cfg/patch-doorstop
```

**Issue**: Permission denied during patch

```bash
# Check permissions
ls -la ~/.local/lib/python*/site-packages/doorstop/

# Fix permissions
chmod +w ~/.local/lib/python*/site-packages/doorstop/
./cfg/patch-doorstop

# Alternative: Use system Python
sudo ./cfg/patch-doorstop /usr/local/lib/python*/site-packages/doorstop
```

## Structure Generation Issues

### Basic Generation Failures

**Issue**: `Cannot find Atlas Home` error

```bash
# Check data directory location
ls -la data/
# Should contain IEC61508, ISO26262, etc.

# If missing, check working directory
pwd
# Should be in standards-atlas root

# Fix path
cd /path/to/standards-atlas
./tools/standards-atlas
```

**Issue**: Git repository errors

```bash
# Error: "not a git repository"
# Solution: Initialize git
cd /output/directory
git init

# Or specify non-git directory
./tools/standards-atlas -d /tmp/test-atlas
```

**Issue**: Permission denied creating output

```bash
# Check permissions
ls -ld /tmp/standards-atlas
# Should be writable

# Fix permissions
sudo chmod 755 /tmp/standards-atlas
sudo chown $USER:$USER /tmp/standards-atlas

# Use alternative directory
./tools/standards-atlas -d ~/my-atlas
```

### Doorstop Generation Errors

**Issue**: Doorstop command not found

```bash
# Check doorstop installation
which doorstop
poetry run which doorstop

# Ensure virtual environment is active
source .venv/bin/activate
./tools/standards-atlas
```

**Issue**: Invalid doorstop document structure

```bash
# Validate existing structure
cd output-directory
doorstop validate

# Clear and regenerate
rm -rf requirements/
./tools/standards-atlas -d $(pwd)
```

**Issue**: HTML publishing fails

```bash
# Check doorstop HTML capabilities
doorstop publish --help

# Test manual publishing
cd output-directory
doorstop publish all requirements

# Check for template issues
doorstop publish all requirements --template custom
```

## AI Processing Issues

### RamaLama Connection Problems

**Issue**: RamaLama server won't start

```bash
# Check RamaLama installation
which ramalama
ramalama --version

# Test manual start
ramalama serve llama3.2:1b

# Check port conflicts
netstat -tlnp | grep :8080
# If occupied, kill conflicting process
sudo kill $(lsof -t -i:8080)

# Use different port
python3 -c "
from tools.IntelliDoc.RamalamaClient import RamaLama
llm = RamaLama('llama3.2:1b', port=8081)
print(llm.query('test'))
"
```

**Issue**: Model download failures

```bash
# Check network connectivity
ping huggingface.co

# Manual model download
ramalama pull llama3.2:1b

# Check disk space
df -h
# Need several GB for models

# Use smaller model
./tools/intellidoc -g -l llama3.2:1b
```

**Issue**: Memory errors during AI processing

```bash
# Check available memory
free -h

# Use smaller model
./tools/intellidoc -g -l llama3.2:1b

# Process in smaller batches
split -l 100 csv/heading-data.csv csv/batch-
for batch in csv/batch-*; do
    ./tools/intellidoc -g -l llama3.2:1b -c $batch
done

# Add swap space (Linux)
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### AI Quality Issues

**Issue**: Generated headings are poor quality

```bash
# Try different model
./tools/intellidoc -g -l nemotron  # Higher quality
./tools/intellidoc -g -l granite3-moe  # Alternative

# Use interactive mode for important clauses
./tools/intellidoc -i -l llama3.1

# Check input data quality
head -20 csv/heading-data.csv
# Ensure clause text is present and meaningful
```

**Issue**: AI processing stuck or very slow

```bash
# Check process status
ps aux | grep ramalama
ps aux | grep intellidoc

# Monitor resource usage
htop

# Kill and restart
pkill -f ramalama
pkill -f intellidoc
./tools/intellidoc -g -l llama3.2:1b

# Check logs
tail -f Tokenizer.log
```

**Issue**: Inconsistent AI responses

```bash
# Clear any cached responses
rm -rf cache/ 2>/dev/null
rm -rf __pycache__/ 2>/dev/null

# Use deterministic settings
python3 << 'EOF'
from tools.IntelliDoc.RamalamaClient import RamaLama
llm = RamaLama("llama3.2:1b")
# Add temperature=0 for deterministic output
response = llm.query("test prompt", temperature=0.1)
EOF
```

## Cross-Standard Mapping Issues

### Link Creation Failures

**Issue**: linkItems fails to create relationships

```bash
# Check mapping file format
head -20 data/mapping01
# Should have proper header and semicolon-separated data

# Validate mapping file syntax
python3 << 'EOF'
with open('data/mapping01', 'r') as f:
    for i, line in enumerate(f):
        if ';' in line and not line.startswith('#'):
            parts = line.strip().split(';')
            if len(parts) != 4:
                print(f"Line {i+1}: Wrong format: {line.strip()}")
EOF

# Check doorstop UIDs exist
doorstop list | head -20
```

**Issue**: Broken cross-references in HTML

```bash
# Regenerate with links
./tools/linkItems /path/to/output
./tools/standards-atlas -n -t -d /path/to/output

# Validate doorstop links
cd /path/to/output
doorstop validate

# Check HTML generation
doorstop publish all requirements
```

**Issue**: Missing bidirectional links

```bash
# Check mapping consistency
python3 << 'EOF'
import csv
relationships = []
with open('data/mapping01', 'r') as f:
    for line in f:
        if ';' in line and not line.startswith('#'):
            parts = line.strip().split(';')
            if len(parts) >= 4:
                relationships.append((parts[0], parts[3]))

# Check for missing reverse relationships
for from_id, to_id in relationships:
    reverse = (to_id, from_id)
    if reverse not in relationships:
        print(f"Missing reverse: {to_id} -> {from_id}")
EOF
```

## Document Reference Issues

### Travelogue Processing Problems

**Issue**: referenceItems fails to find references

```bash
# Check travelogue directory
ls -la travelogue/
# Should contain .md files

# Check reference patterns
grep -n "ISO.*:.*[0-9]" travelogue/*.md
grep -n "IEC.*:.*[0-9]" travelogue/*.md
grep -n "EN.*:.*[0-9]" travelogue/*.md

# Test manual reference
python3 << 'EOF'
import re
pattern = r"(ISO|IEC|EN)\s*[0-9]+.*:[0-9]{4}\s+[0-9]+\.[0-9]+"
text = "According to ISO 26262-6:2018 5.4.1"
match = re.search(pattern, text)
print(f"Found: {match.group(0) if match else 'No match'}")
EOF
```

**Issue**: Broken links in travelogue output

```bash
# Check UID mapping file
head -20 csv/uid-ref-map.csv
# Format: hash;doorstop-uid;clause-reference

# Verify mapping consistency
python3 << 'EOF'
import csv
mappings = {}
with open('csv/uid-ref-map.csv', 'r') as f:
    reader = csv.reader(f, delimiter=';')
    for row in reader:
        if len(row) >= 3:
            mappings[row[2]] = row[1]

print(f"Loaded {len(mappings)} clause mappings")
# Check for specific reference
test_ref = "ISO 26262-6:2018 5.4.1"
print(f"Mapping for '{test_ref}': {mappings.get(test_ref, 'NOT FOUND')}")
EOF
```

**Issue**: Reference format not recognized

```bash
# Check supported reference formats
python3 << 'EOF'
import re

# Current pattern from referenceItems
patterns = [
    r"(\b|\W)([A-Z\s]+\s+\d\d\d\d\d?)-?(\d*):\d\d\d\d\s+([1-9A-Z][0-9.]*)",
    r"(ISO|IEC|EN)\s*[0-9]+-?[0-9]*:[0-9]{4}\s+[0-9]+(\.[0-9]+)*",
    r"(ISO|IEC|EN)\s*[0-9]+-?[0-9]*\s+[0-9]+(\.[0-9]+)*"
]

test_refs = [
    "ISO 26262-6:2018 5.4.1",
    "IEC 61508-3:2010 7.4.2",
    "EN 50129:2003 4.3.2.1",
    "ISO26262-6:2018 5.4.1",  # No space
    "ISO 26262 Part 6 5.4.1"  # Different format
]

for pattern in patterns:
    regex = re.compile(pattern)
    print(f"Pattern: {pattern}")
    for ref in test_refs:
        match = regex.search(ref)
        print(f"  '{ref}': {'✓' if match else '✗'}")
    print()
EOF
```

## Performance Issues

### Slow Processing

**Issue**: Structure generation is very slow

```bash
# Profile doorstop performance
time ./tools/standards-atlas -d /tmp/test

# Check for large files
du -sh data/*
ls -la data/

# Process standards individually
for std in IEC61508 ISO26262 EN50129; do
    echo "Processing $std..."
    time grep "$std" data/* | head -100
done
```

**Issue**: AI processing takes too long

```bash
# Use faster model
./tools/intellidoc -g -l llama3.2:1b

# Process smaller batches
head -50 csv/heading-data.csv > csv/test-batch.csv
./tools/intellidoc -g -l nemotron -c csv/test-batch.csv

# Monitor progress
tail -f Tokenizer.log &
./tools/intellidoc -g -l nemotron

# Estimate completion time
python3 << 'EOF'
import csv
clause_count = 0
with open('csv/heading-data.csv', 'r') as f:
    clause_count = sum(1 for line in f)
    
# Estimate: 5 seconds per clause for nemotron
minutes = (clause_count * 5) / 60
print(f"Estimated time: {minutes:.1f} minutes for {clause_count} clauses")
EOF
```

### Memory Issues

**Issue**: Out of memory errors

```bash
# Check memory usage
free -h
ps aux --sort=-%mem | head -10

# Use memory-efficient models
./tools/intellidoc -g -l llama3.2:1b

# Process in smaller chunks
python3 << 'EOF'
import csv

# Split large CSV into chunks
chunk_size = 50
chunk_num = 0

with open('csv/heading-data.csv', 'r') as f:
    reader = csv.reader(f)
    
    chunk = []
    for row in reader:
        chunk.append(row)
        
        if len(chunk) >= chunk_size:
            with open(f'csv/chunk-{chunk_num:03d}.csv', 'w') as out:
                writer = csv.writer(out)
                writer.writerows(chunk)
            chunk = []
            chunk_num += 1
    
    # Write remaining rows
    if chunk:
        with open(f'csv/chunk-{chunk_num:03d}.csv', 'w') as out:
            writer = csv.writer(out)
            writer.writerows(chunk)

print(f"Created {chunk_num + 1} chunks")
EOF

# Process chunks individually
for chunk in csv/chunk-*.csv; do
    echo "Processing $chunk..."
    ./tools/intellidoc -g -l llama3.2:1b -c "$chunk"
done
```

### Disk Space Issues

**Issue**: Insufficient disk space

```bash
# Check disk usage
df -h
du -sh ~/.cache/
du -sh .venv/

# Clean up space
# Remove old model files
rm -rf ~/.cache/ramalama/old-models/

# Clean Python cache
find . -name "__pycache__" -exec rm -rf {} +
find . -name "*.pyc" -delete

# Clean poetry cache
poetry cache clear --all pypi

# Use external storage for models
export RAMALAMA_MODEL_PATH=/external/drive/models
./tools/intellidoc -g -l llama3.2:1b
```

## Network and Connectivity Issues

### Model Download Problems

**Issue**: Cannot download AI models

```bash
# Check network connectivity
ping huggingface.co
curl -I https://huggingface.co

# Check proxy settings
echo $http_proxy
echo $https_proxy

# Set proxy if needed
export http_proxy=http://proxy.example.com:8080
export https_proxy=https://proxy.example.com:8080

# Manual download with curl
curl -L "https://huggingface.co/microsoft/DialoGPT-medium/resolve/main/pytorch_model.bin" -o model.bin

# Use offline mode
./tools/intellidoc -g -l /path/to/local/model
```

**Issue**: Firewall blocking connections

```bash
# Check firewall status
sudo ufw status  # Ubuntu
sudo firewall-cmd --list-all  # CentOS/RHEL

# Allow RamaLama ports
sudo ufw allow 8080
sudo firewall-cmd --add-port=8080/tcp

# Test local connection
telnet localhost 8080
curl http://localhost:8080/health
```

## Data Integrity Issues

### Corrupted Data Files

**Issue**: Standard definition files corrupted

```bash
# Validate data file syntax
for file in data/*; do
    echo "Checking $file..."
    bash -n "$file" 2>/dev/null || echo "Syntax error in $file"
done

# Check for required fields
grep -L "name=" data/* && echo "Missing name field"
grep -L "structure=" data/* && echo "Missing structure field"

# Restore from git
git checkout data/
```

**Issue**: CSV files malformed

```bash
# Validate CSV format
python3 << 'EOF'
import csv

def validate_csv(filename):
    try:
        with open(filename, 'r') as f:
            reader = csv.reader(f, delimiter=';')
            for i, row in enumerate(reader):
                if i == 0:
                    print(f"{filename}: {len(row)} columns")
                if len(row) != 4 and len(row) != 5:
                    print(f"  Line {i+1}: Wrong column count: {len(row)}")
                    if i > 10:  # Limit output
                        break
    except Exception as e:
        print(f"Error reading {filename}: {e}")

validate_csv('csv/heading-data.csv')
validate_csv('csv/uid-ref-map.csv')
EOF

# Regenerate CSV files
rm csv/*.csv
./tools/standards-atlas -c -d $(pwd)
```

## Integration Issues

### Version Conflicts

**Issue**: Conflicting package versions

```bash
# Check installed versions
poetry show
pip list | grep -E "(doorstop|ramalama|llama)"

# Update to compatible versions
poetry update

# Fix specific conflicts
poetry remove problematic-package
poetry add problematic-package@compatible-version

# Use fresh environment
rm -rf .venv
poetry install
```

**Issue**: Python version incompatibility

```bash
# Check Python version requirements
grep python pyproject.toml
python3 --version

# Install compatible Python version
pyenv install 3.11.0
pyenv local 3.11.0
poetry env use 3.11.0
poetry install
```

## Recovery Procedures

### Complete Reset

When nothing else works:

```bash
# Save your custom data
cp -r data/mapping* /tmp/backup/
cp -r travelogue/ /tmp/backup/

# Clean installation
rm -rf .venv
rm -rf __pycache__
rm -rf tools/IntelliDoc/__pycache__
poetry install

# Reapply patches
./cfg/patch-doorstop

# Test basic functionality
./tools/standards-atlas --help
python3 -c "from tools.IntelliDoc.RamalamaClient import RamaLama; print('OK')"

# Restore custom data
cp /tmp/backup/mapping* data/
cp -r /tmp/backup/travelogue .
```

### Emergency Backup

```bash
# Create complete backup
tar -czf standards-atlas-backup-$(date +%Y%m%d).tar.gz \
    --exclude=.venv \
    --exclude=__pycache__ \
    --exclude="*.pyc" \
    .

# Restore from backup
tar -xzf standards-atlas-backup-YYYYMMDD.tar.gz
source setup.sh
```

## Getting Help

### Diagnostic Information

When reporting issues, include:

```bash
# System information
echo "=== System Information ==="
uname -a
python3 --version
poetry --version
doorstop --version 2>/dev/null || echo "Doorstop not found"

# Environment
echo "=== Environment ==="
echo "VIRTUAL_ENV: $VIRTUAL_ENV"
echo "PYTHONPATH: $PYTHONPATH"
echo "Working directory: $(pwd)"

# Package versions
echo "=== Package Versions ==="
poetry show | head -20

# Recent logs
echo "=== Recent Logs ==="
tail -20 Tokenizer.log 2>/dev/null || echo "No Tokenizer.log found"
```

### Support Channels

1. **GitHub Issues**: Report bugs with diagnostic information
2. **Documentation**: Check [Architecture](architecture.md) and [CLI Reference](cli-reference.md)
3. **Community**: Share solutions and ask questions
4. **Logs**: Always include relevant log files with issue reports

### Self-Diagnosis Checklist

Before seeking help:

- [ ] Run system health check
- [ ] Check virtual environment is active
- [ ] Verify all dependencies installed
- [ ] Test with minimal example
- [ ] Check disk space and memory
- [ ] Review recent changes
- [ ] Try alternative approaches (different models, smaller datasets)
- [ ] Search existing issues and documentation

---

*Most issues can be resolved by following these troubleshooting steps. For persistent problems, the diagnostic information will help identify the root cause quickly.*