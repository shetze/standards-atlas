# RamaLama Migration Guide

This guide helps you migrate from Ollama to RamaLama in the Standards Atlas project.

## Overview

Standards Atlas has migrated from Ollama to RamaLama for local LLM operations. RamaLama provides better integration, automatic model management, and improved resource handling.

## What Changed

### Before (Ollama)
```python
import ollama
response = ollama.generate(model="nemotron", prompt="...")
result = response["response"]
```

### After (RamaLama)
```python
from IntelliDoc.RamalamaClient import RamaLama
llm = RamaLama("nemotron")
result = llm.query("...")
```

## Migration Steps

### 1. Remove Ollama Dependencies

If you have Ollama installed and want to switch completely:

```bash
# Stop Ollama service (if running)
sudo systemctl stop ollama  # On Linux with systemd
# or
brew services stop ollama   # On macOS with Homebrew

# Optional: Remove Ollama (if no longer needed)
# Follow Ollama uninstall instructions for your platform
```

### 2. Install RamaLama

RamaLama is already included in the project dependencies:

```bash
# Install project dependencies
source setup.sh
```

Or if using Poetry directly:
```bash
poetry install
```

### 3. Model Compatibility

| Ollama Model | RamaLama Equivalent | Notes |
|--------------|---------------------|-------|
| `nemotron` | `nemotron` | Same model, different backend |
| `llama3.1` | `llama3.1` | Compatible |
| `llama3.2:1b` | `llama3.2:1b` | Recommended for testing |
| `granite3-moe` | `granite3-moe` | Available |
| `granite3-dense` | `granite3-dense` | Available |

### 4. Configuration Changes

#### Old Configuration (Ollama)
```python
# Direct ollama calls
response = ollama.generate(
    model="nemotron",
    prompt="create a heading for: ...",
)
```

#### New Configuration (RamaLama)
```python
# Using RamaLama client
from IntelliDoc.RamalamaClient import RamaLama

# Basic usage
llm = RamaLama("nemotron")
response = llm.query("create a heading for: ...")

# With options
response = llm.query(
    "create a heading for: ...",
    max_tokens=100,
    temperature=0.7
)

# Streaming
for chunk in llm.stream("Tell me about safety standards"):
    print(chunk, end="", flush=True)
```

## Key Differences

### Automatic Server Management
- **Ollama**: Required manual server management
- **RamaLama**: Automatically starts/stops servers as needed

### Model Downloads
- **Ollama**: Manual model pulling required
- **RamaLama**: Automatic model download on first use

### Resource Management
- **Ollama**: Manual resource cleanup
- **RamaLama**: Automatic cleanup with context managers

### API Differences
- **Ollama**: Returns `{"response": "text"}` objects
- **RamaLama**: Returns direct text responses

## Troubleshooting

### Common Issues

#### Port Conflicts
If you get port conflicts:
```python
# Use a different port
llm = RamaLama("nemotron", port=8081)
```

#### Model Not Found
```bash
# RamaLama will automatically download models
# No manual intervention needed (unlike Ollama)
```

#### Performance Issues
```python
# Use smaller model for testing
llm = RamaLama("llama3.2:1b")  # Faster inference

# Enable debug mode to see what's happening
llm = RamaLama("nemotron", debug=True)
```

#### Memory Issues
```python
# Use context manager for automatic cleanup
with RamaLama("nemotron") as llm:
    result = llm.query("...")
# Server automatically cleaned up
```

## Testing the Migration

Use the provided test script to verify your setup:

```bash
python test_ramalama.py
```

This will:
1. Test RamaLama import
2. Start a model server
3. Run a simple query
4. Clean up resources

## Backward Compatibility

The migration maintains compatibility with existing IntelliDoc workflows:

- `HeadingFactory` class works unchanged
- `Summarizer` class works unchanged  
- `LLM` class provides compatibility methods
- Command-line tools work as before

## Performance Comparison

| Aspect | Ollama | RamaLama |
|--------|--------|----------|
| Setup Complexity | Manual | Automatic |
| Resource Management | Manual | Automatic |
| Model Management | Manual pull | Auto-download |
| Memory Usage | Variable | Optimized |
| Error Handling | Basic | Enhanced |

## Next Steps

After migration:

1. **Test Your Workflows**: Run your existing IntelliDoc workflows to ensure compatibility
2. **Optimize Models**: Experiment with different models for your use case
3. **Monitor Performance**: Check resource usage and adjust model choices
4. **Update Scripts**: Consider using new RamaLama features in custom scripts

## Support

If you encounter issues:

1. Enable debug mode: `RamaLama("model", debug=True)`
2. Check the test script works: `python test_ramalama.py`
3. Review the RamaLama client code: `tools/IntelliDoc/RamalamaClient.py`
4. Check project issues on GitHub

## Future Improvements

The RamaLama integration opens up possibilities for:

- Multiple concurrent model instances
- Better resource scheduling
- Enhanced error recovery
- Model performance profiling
- Custom model configurations

---

*This migration was completed to improve reliability, resource management, and user experience while maintaining full backward compatibility.*