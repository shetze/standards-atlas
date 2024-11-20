from llama_index.llms.ollama import Ollama

class LLM:
    def __init__(self, model = 'llama3.1'):
        kwargs = {
                "tfs_z": 1.0,
                "top_k": 40,
                "top_p": 0.9,
                "repeat_last_n": 64,
                "repeat_penalty": 1.2,
            }
        llm = Ollama(
                model=model,
                base_url='http://localhost:11434',
                temperature=0.1,
                context_window=3900,
                additional_kwargs=kwargs,
                request_timeout=360.0,
                )
        self.llm = llm



