#!/usr/bin/env python3
"""
Test script for RamaLama integration
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'tools'))

from IntelliDoc.RamalamaClient import RamaLama

def test_ramalama():
    """Test basic RamaLama functionality"""
    print("Testing RamaLama client...")
    
    try:
        # Test with a small model
        with RamaLama("llama3.2:1b", debug=True) as llm:
            print("\n--- Testing simple query ---")
            response = llm.query("What is 2+2?", max_tokens=50)
            print(f"Response: {response}")
            return True
    except Exception as e:
        print(f"Test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_ramalama()
    if success:
        print("\n✓ RamaLama integration test passed!")
    else:
        print("\n✗ RamaLama integration test failed!")
        sys.exit(1)