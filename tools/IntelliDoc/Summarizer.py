"""Summarizer module for generating AI-powered summaries of standard clauses.

This module provides functionality to generate summaries for standard clauses
using local LLM models through RamaLama integration.
"""

import re
import logging
import json
from typing import List, Dict, Optional, Any
from natsort import natsorted
from .RamalamaClient import RamaLama

logger = logging.getLogger(__name__)


class Summarizer:
    """AI-powered summarizer for standard clauses.
    
    Uses local LLM models via RamaLama to generate meaningful summaries
    of standard clauses and requirements.
    """
    # Model-specific patterns to filter out unwanted response formatting
    skip_pattern: Dict[str, str] = {
        "llama3.1": r".*summary.*",
        "nemotron": r"^[1-9]\.\s+\*+([\w\s.&-/]+)\*+",
        "granite3-moe": r'^[^"]*"(.+)"\W?$',
        "granite3-dense": r'^[^"]*"(.+)"\W?$',
        "hf.co/ibm-granite/granite-8b-code-instruct-4k-GGUF": r'^[^"]*"(.+)"\W?$',
    }

    def __init__(self, model: str) -> None:
        """Initialize the Summarizer with a specific model.
        
        Args:
            model: Name of the LLM model to use for summarization
        """
        self.model = model if model in Summarizer.skip_pattern else "nemotron"
        self.skip_regex = re.compile(Summarizer.skip_pattern[self.model], re.IGNORECASE)
        self.sumstore: Dict[str, List[str]] = {}
        self.llm_client = RamaLama(self.model)

    def request(self, prompt: str, question: str, text: str, verbose: bool = False) -> List[str]:
        """Generate a response to a question about given text.
        
        Args:
            prompt: System prompt for the LLM
            question: Specific question to ask
            text: Context text to analyze
            verbose: Enable verbose output
            
        Returns:
            List of response lines, filtered and cleaned
        """
        if not text.strip():
            return []
        
        reply: List[str] = []
        attempt = 0
        request_text = f"System: {prompt}:\n\nContext: {text}\n\nQuestion: {question}"
        while not reply:
            response_text = self.llm_client.query(request_text)
            
            # Filter and clean response lines
            for line in response_text.splitlines():
                if not self.skip_regex.match(line, re.IGNORECASE):
                    reply.append(line)
            
            # Remove empty lines from start and end
            while reply and not reply[0].strip():
                reply.pop(0)
            while reply and not reply[-1].strip():
                reply.pop(-1)

            attempt += 1
            if verbose:
                self._log_attempt("reply", attempt, prompt, reply)
            
            if attempt > 5:
                logger.warning(f"No reply from {self.model} after {attempt} attempts")
                break
                
        return reply

    def summarize(self, clause: Any, text: str, verbose: bool = False) -> List[str]:
        """Generate a summary for a standard clause.
        
        Args:
            clause: Clause object containing metadata
            text: Text content to summarize
            verbose: Enable verbose output
            
        Returns:
            List of summary lines
        """
        if not text.strip():
            return []
            
        clause_type = clause.clauseType()
        clause_id = clause.structure.ID
        prompt = f"create a plain summary for the following {clause_type}. Do not add any introduction, question or comments: {text}"
        
        summary: List[str] = []
        attempt = 0
        while not summary:
            response_text = self.llm_client.query(prompt)
            
            # Filter and clean response lines
            for line in response_text.splitlines():
                if not self.skip_regex.match(line, re.IGNORECASE):
                    summary.append(line)
            
            # Remove empty lines from start and end
            while summary and not summary[0].strip():
                summary.pop(0)
            while summary and not summary[-1].strip():
                summary.pop(-1)

            attempt += 1
            if verbose:
                self._log_attempt("summary", attempt, prompt, summary, clause_id)
            
            if attempt > 5:
                logger.warning(f"No summary from {self.model} after {attempt} attempts")
                break
                
        self.sumstore[clause_id] = summary
        return summary

    def generate_summaries(self, clause: Any, cache_file: Optional[str] = None, 
                          force: bool = False, verbose: bool = False) -> None:
        """Generate summaries for a clause and optionally cache them.
        
        Args:
            clause: Clause object to generate summaries for
            cache_file: Optional file to cache results
            force: Force regeneration even if already summarized
            verbose: Enable verbose output
        """
        if clause.isSummarized() and not force:
            return
            
        summary = self.summarize(clause, clause.getText(), verbose)
        
        # Add summary lines to clause
        for line in summary:
            clause.summary.append(line)
            
        if cache_file is not None:
            self._write_to_cache(cache_file, clause.structure.ID, summary)

    def summaries4all(self, clause_index: Dict[str, Any], cache_file: Optional[str] = None, 
                     force: bool = False, verbose: bool = False) -> None:
        """Generate summaries for all clauses in an index.
        
        Args:
            clause_index: Dictionary mapping clause IDs to clause objects
            cache_file: Optional file to cache results
            force: Force regeneration even if already summarized
            verbose: Enable verbose output
        """
        for clause_id in clause_index:
            clause = clause_index[clause_id]
            if clause.isSummarized() and not force:
                continue
            self.generate_summaries(clause, cache_file, force, verbose)

    def dump_sumstore(self, cache_file: str = "sumstore.json") -> None:
        """Dump the summary store to a JSON file.
        
        Args:
            cache_file: File path to write the summary store
        """
        try:
            with open(cache_file, "a") as store:
                json.dump(
                    self.sumstore,
                    store,
                    default=lambda o: o.__dict__,
                    sort_keys=True,
                    indent=4,
                )
        except IOError as e:
            logger.warning(f"Failed to write summary store: {e}")

    def load_summaries_from_file(self, clause_index: Dict[str, Any], cache_file: str) -> None:
        """Load cached summaries from a file.
        
        Args:
            clause_index: Dictionary mapping clause IDs to clause objects
            cache_file: File path to read cached summaries from
        """
        try:
            with open(cache_file, "r") as store:
                current_clause = None
                for line in store:
                    if re.match("^#", line):
                        clause_id = line[2:].rstrip()
                        if clause_id in clause_index:
                            current_clause = clause_index[clause_id]
                    elif current_clause is not None:
                        current_clause.summary.append(line.rstrip())
        except IOError as e:
            logger.warning(f"Failed to load summaries: {e}")
    
    def _log_attempt(self, operation: str, attempt: int, prompt: str, 
                    result: List[str], clause_id: Optional[str] = None) -> None:
        """Log verbose information about generation attempts.
        
        Args:
            operation: Type of operation (e.g., 'summary', 'reply')
            attempt: Attempt number
            prompt: The prompt used
            result: Generated result
            clause_id: Optional clause ID for context
        """
        separator = "-" * 45
        context = f" for {clause_id}" if clause_id else ""
        print(f"\n\n{separator}")
        print(f"Generate {operation}{context} attempt {attempt}")
        print(f"{prompt}")
        print(f"{separator}")
        print("\n".join(result))
    
    def _write_to_cache(self, cache_file: str, clause_id: str, summary: List[str]) -> None:
        """Write summary to cache file.
        
        Args:
            cache_file: File path to write to
            clause_id: ID of the clause
            summary: Summary lines to write
        """
        try:
            with open(cache_file, "a") as store:
                store.write(f"# {clause_id}\n")
                for line in summary:
                    store.write(f"{line}\n")
                store.write("\n\n")
        except IOError as e:
            logger.warning(f"Failed to write cache: {e}")
