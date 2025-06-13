"""
RamaLama Python Client Module

Simple integration for RamaLama AI Models

Usage:
    from ramalama_client import RamaLama
    
    # Simple usage
    llm = RamaLama("llama3.2:1b")
    response = llm.query("Explain Python to me")
    print(response)
    
    # With options
    response = llm.query("Write a story", max_tokens=200, temperature=0.8)
    
    # Streaming
    for chunk in llm.stream("Tell me a joke"):
        print(chunk, end="", flush=True)
"""

import requests
import json
import subprocess
import time
from typing import Iterator, Optional, Dict, Any
import atexit
import signal
import os


class RamaLamaError(Exception):
    """Custom exception for RamaLama errors"""
    pass


class RamaLama:
    def __init__(self, model_name: str, host: str = "127.0.0.1", port: int = 8080, auto_stop: bool = True, debug: bool = False):
        """
        Initialize RamaLama client
        
        Args:
            model_name: Name of the model (e.g., "llama3.2:1b")
            host: Server host (default: "127.0.0.1")
            port: Server port (default: 8080)
            auto_start: Automatically start server if not reachable
            auto_stop: Automatically stop server on exit
            debug: Enable debug output
        """
        self.model_name = model_name
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.auto_stop = auto_stop
        self.debug = debug
        self.server_process = None
        
        if self.debug:
            print(f"[DEBUG] Initializing RamaLama client for model: {model_name}")
            print(f"[DEBUG] Base URL: {self.base_url}")
        
        if auto_stop:
            atexit.register(self._cleanup)
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)
        
        if not self._is_server_running():
            self._start_server()
    
    def _signal_handler(self, signum, frame):
        """Signal handler for graceful shutdown"""
        self._cleanup()
    
    def _cleanup(self):
        """Terminate server process"""
        if self.server_process and self.server_process.poll() is None:
            if self.debug:
                print(f"[DEBUG] Terminating RamaLama server (PID: {self.server_process.pid})")
            # Terminate the entire process group started with start_new_session
            try:
                os.killpg(os.getpgid(self.server_process.pid), signal.SIGTERM)
            except ProcessLookupError:
                 pass # Process might already be gone
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if self.debug:
                    print("[DEBUG] Server didn't terminate gracefully, killing...")
                os.killpg(os.getpgid(self.server_process.pid), signal.SIGKILL)
            self.server_process = None
    
    def _is_server_running(self) -> bool:
        """Check if RamaLama server is reachable."""
        if self.debug:
            print(f"[DEBUG] Checking if server is running at {self.base_url}")
        try:
            # A simple GET request to a common endpoint. We expect any response, even an error.
            response = requests.get(f"{self.base_url}/health", timeout=2, headers={'Connection': 'close'})
            if self.debug:
                print(f"[DEBUG] Server check successful with status: {response.status_code}")
            return True
        except requests.exceptions.RequestException:
            if self.debug:
                print(f"[DEBUG] Nothing listening on {self.host}:{self.port}")
            return False

    def _start_server(self):
        """
        Start RamaLama server, read its stdout to detect when it's ready,
        and dynamically parse the port it's actually using.
        """
        print(f"Starting RamaLama server for model: {self.model_name}")
        
        # Do not specify the port, let the server choose a free one.
        cmd = [
            'ramalama', 'serve',
            '--host', self.host,
            self.model_name
        ]
        
        if self.debug:
            print(f"[DEBUG] Running command: {' '.join(cmd)}")
            
        try:
            self.server_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                start_new_session=True  # Detach from parent terminal
            )

            if self.debug:
                print(f"[DEBUG] Server process started with PID: {self.server_process.pid} in a new session.")

            listen_string = "HTTP server is listening"
            ready_string = "starting the main loop"
            max_wait_seconds = 300
            
            print(f"Waiting for server to become ready (max: {max_wait_seconds}s)...")
            
            found_listen_string = False
            start_time = time.time()
            
            while time.time() - start_time < max_wait_seconds:
                if self.server_process.poll() is not None:
                    output = self.server_process.stdout.read()
                    raise RamaLamaError(f"Server process died. Exit code: {self.server_process.returncode}\nOutput:\n{output}")

                line = self.server_process.stdout.readline()
                if not line:
                    time.sleep(0.1)
                    continue

                if self.debug:
                    print(f"[SERVER] {line.strip()}")
                
                if not found_listen_string and listen_string in line:
                    try:
                        port_str = line.split('port: ')[1].split(',')[0]
                        self.port = int(port_str)
                        self.base_url = f"http://{self.host}:{self.port}"
                        if self.debug:
                            print(f"[DEBUG] Server is using port {self.port}. Client updated.")
                        found_listen_string = True
                    except (IndexError, ValueError) as e:
                        raise RamaLamaError(f"Could not parse port from output: '{line}'. Error: {e}")

                if found_listen_string and ready_string in line:
                    print(f"\n✓ RamaLama server is ready at {self.base_url} (PID: {self.server_process.pid})\n")
                    time.sleep(1) # Give it a moment to stabilize
                    return

            raise RamaLamaError(f"Server did not become ready within {max_wait_seconds} seconds.")

        except Exception as e:
            self._cleanup()
            raise RamaLamaError(f"Error starting server: {e}")

    def query(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7, 
              stop_sequences: Optional[list] = None, **kwargs) -> str:
        """
        Simple query to the model by trying multiple endpoints and payload formats.
        """
        payload = {"prompt": prompt, "n_predict": max_tokens, "temperature": temperature, "stop": stop_sequences or ["</s>", "<|end|>", "<|endoftext|>"], "stream": False, **kwargs}
        
        endpoint= "/completion"
        headers = {'Content-Type': 'application/json', 'Connection': 'close'}

        try:
            if self.debug:
                print(f"[DEBUG] Trying {endpoint} with payload: {json.dumps(payload, indent=2)}")
                    
            response = requests.post(
                f"{self.base_url}{endpoint}",
                json=payload,
                headers=headers,
                timeout=120
            )
                    
            if self.debug:
                print(f"[DEBUG] Response status for {endpoint}: {response.status_code}")
                if response.text:
                    print(f"[DEBUG] Response text: {response.text[:300]}...")
                    
            if response.status_code == 200:
                result = response.json()
                if 'content' in result:
                    return result['content'].strip()
                elif 'choices' in result and len(result['choices']) > 0:
                    choice = result['choices'][0]
                    if 'text' in choice:
                        return choice['text'].strip()
                    elif 'message' in choice and 'content' in choice['message']:
                        return choice['message']['content'].strip()
                elif 'text' in result:
                    return result['text'].strip()
                elif 'response' in result:
                    return result['response'].strip()
                else:
                    return str(result)
                    
        except requests.exceptions.RequestException as e:
            if self.debug:
                print(f"[DEBUG] Request failed for {endpoint}: {e}")
        except json.JSONDecodeError as e:
            if self.debug:
                print(f"[DEBUG] JSON decode error for {endpoint}: {e}. Response: {response.text}")
        
        raise RamaLamaError("Unable to get response from server with any endpoint/payload combination.")

    def stream(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7,
               stop_sequences: Optional[list] = None, **kwargs) -> Iterator[str]:
        """
        Streaming query - returns response token by token
        """
        payload = {
            "prompt": prompt,
            "n_predict": max_tokens,
            "temperature": temperature,
            "stop": stop_sequences or ["</s>", "<|end|>", "<|endoftext|>"],
            "stream": True,
            **kwargs
        }
        headers = {'Content-Type': 'application/json', 'Connection': 'close'}

        try:
            response = requests.post(
                f"{self.base_url}/completion",
                json=payload,
                headers=headers,
                stream=True,
                timeout=120
            )
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        json_str = line_str[6:]
                        if json_str.strip() == '[DONE]':
                            break
                        try:
                            data = json.loads(json_str)
                            if 'content' in data:
                                yield data['content']
                            elif 'choices' in data and len(data['choices']) > 0:
                                delta = data['choices'][0].get('delta', {})
                                if 'content' in delta:
                                    yield delta['content']
                        except json.JSONDecodeError:
                            continue
                    else:
                        try:
                            data = json.loads(line_str)
                            if 'content' in data:
                                yield data['content']
                        except json.JSONDecodeError:
                            continue
                            
        except requests.exceptions.RequestException as e:
            raise RamaLamaError(f"Streaming error: {e}")

    def chat(self, messages: list, max_tokens: int = 512, temperature: float = 0.7, **kwargs) -> str:
        """Chat interface with message history"""
        prompt_parts = []
        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            if role == 'user':
                prompt_parts.append(f"Human: {content}")
            elif role == 'assistant':
                prompt_parts.append(f"Assistant: {content}")
            else:
                prompt_parts.append(f"{role}: {content}")
        
        prompt_parts.append("Assistant:")
        prompt = "\n".join(prompt_parts)
        
        return self.query(prompt, max_tokens, temperature, **kwargs)
    
    def __enter__(self):
        """Context manager support"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup"""
        if self.auto_stop:
            self._cleanup()

# Convenience functions for simple usage
def query(model_name: str, prompt: str, **kwargs) -> str:
    with RamaLama(model_name) as llm:
        return llm.query(prompt, **kwargs)

def stream(model_name: str, prompt: str, **kwargs) -> Iterator[str]:
    with RamaLama(model_name) as llm:
        yield from llm.stream(prompt, **kwargs)

# Example usage
if __name__ == "__main__":
    try:
        print("=== RamaLama Client Example ===")
        with RamaLama("llama3.2:1b", debug=True) as llm:
            print("\n--- Simple Query ---")
            response = llm.query("Explain the importance of bees in one sentence.")
            print(f"Response: {response}")

            print("\n--- Streaming Query ---")
            print("Response: ", end="", flush=True)
            for chunk in llm.stream("Tell a short, happy story about a robot."):
                print(chunk, end="", flush=True)
            print("\n")

    except RamaLamaError as e:
        print(f"\nAN ERROR OCCURRED: {e}")