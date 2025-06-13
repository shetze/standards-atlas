from IntelliDoc.RamalamaClient import RamaLama

# Connect to existing server without auto-start
with RamaLama("llama3.2:1b", debug=True) as llm:
    response = llm.query("Explain Python in 2 sentences")
    print(response)

print("\nScript finished.")