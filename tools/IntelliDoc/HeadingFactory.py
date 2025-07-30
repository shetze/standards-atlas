"""HeadingFactory module for generating AI-powered headings for standard clauses.

This module provides functionality to generate meaningful headings for standard
clauses using local LLM models through RamaLama integration.
"""

import re
import logging
import json
from typing import List, Dict, Optional, Any
from natsort import natsorted
from .Clause import Clause, ClauseID, ClauseHeading
from .RamalamaClient import RamaLama

logger = logging.getLogger(__name__)


class HeadingFactory:
    """AI-powered heading generator for standard clauses.
    
    Uses local LLM models via RamaLama to generate concise, meaningful
    headings for standard clauses that lack descriptive titles.
    """
    # Model-specific regex patterns to extract headings from LLM responses
    hl_pattern: Dict[str, str] = {
        "llama3.1": r'^[^"]*"(.+)"\W?$',
        "nemotron": r"^[1-9]\.\s+\*+([\w\s.&-/]+)\*+",
        "granite3-moe": r'^[^"]*"(.+)"\W?$',
        "granite3-dense": r'^[^"]*"(.+)"\W?$',
        "hf.co/ibm-granite/granite-8b-code-instruct-4k-GGUF": r'^[^"]*"(.+)"\W?$',
    }

    def __init__(self, model: str) -> None:
        """Initialize the HeadingFactory with a specific model.
        
        Args:
            model: Name of the LLM model to use for heading generation
        """
        self.heading_words = 3
        self.model = model if model in HeadingFactory.hl_pattern else "nemotron"
        self.hl_regex = re.compile(HeadingFactory.hl_pattern[self.model])
        self.llm_client = RamaLama(self.model)

    def generate_headings(self, clause: Any, verbose: bool = False) -> List[str]:
        """Generate heading suggestions for a clause.
        
        Args:
            clause: Clause object containing text and metadata
            verbose: Enable verbose output
            
        Returns:
            List of suggested headings
        """
        text = clause.getText()
        if not text.strip():
            return []
            
        clause_type = clause.clauseType()
        prompt = f"create a max {self.heading_words} word headline for the following {clause_type}: {text}"
        
        headings: List[str] = []
        attempt = 0
        while not headings:
            response_text = self.llm_client.query(prompt)
            
            # Extract headings using model-specific regex
            for line in response_text.splitlines():
                match = self.hl_regex.match(line)
                if match:
                    headings.append(match[1])
                    
            attempt += 1
            if verbose:
                self._log_attempt(clause.structure.ID, attempt, prompt, response_text)
                
            if attempt > 5:
                logger.warning(f"No headings from {self.model} after {attempt} attempts")
                break
                
        return headings

    def generate_alternative_headings(self, clause: Any, cache_file: Optional[str] = None, 
                                     force: bool = False, verbose: bool = False) -> None:
        """Generate and store alternative headings for a clause.
        
        Args:
            clause: Clause object to generate headings for
            cache_file: Optional file to cache results
            force: Force regeneration even if clause already has specific heading
            verbose: Enable verbose output
        """
        if clause.heading.isSpecific() and not force:
            return
            
        alternatives = self.generate_headings(clause, verbose)
        
        # Add alternatives to the clause heading
        for heading in alternatives:
            clause.heading.addAlternative(heading, "generated", self.model)
            
        if cache_file is not None:
            self._write_to_cache(cache_file, clause.structure.ID, alternatives)

    def headings4all(self, cache_file: Optional[str] = None, force: bool = False, 
                    verbose: bool = False) -> None:
        """Generate headings for all clauses in the global clause index.
        
        Args:
            cache_file: Optional file to cache results
            force: Force regeneration even if clauses already have specific headings
            verbose: Enable verbose output
        """
        for clause_id in Clause.clauseIndex:
            clause = Clause.clauseIndex[clause_id]
            if clause.heading.isSpecific() and not force:
                continue
            self.generate_alternative_headings(clause, cache_file, force, verbose)

    def load_alternatives_from_file(self, cache_file: str) -> None:
        """Load cached heading alternatives from a file.
        
        Args:
            cache_file: File path to read cached headings from
        """
        try:
            current_clause_id = None
            with open(cache_file, "r") as store:
                for line in store:
                    if re.match("^#", line):
                        current_clause_id = line[2:].rstrip()
                    elif current_clause_id:
                        match = self.hl_regex.match(line)
                        if match and current_clause_id in Clause.clauseIndex:
                            clause = Clause.clauseIndex[current_clause_id]
                            clause.heading.addAlternative(
                                match[1], "generated", self.model
                            )
        except IOError as e:
            logger.warning(f"Failed to load headings: {e}")
    
    def _log_attempt(self, clause_id: str, attempt: int, prompt: str, response: str) -> None:
        """Log verbose information about heading generation attempts.
        
        Args:
            clause_id: ID of the clause being processed
            attempt: Attempt number
            prompt: The prompt used
            response: Generated response
        """
        print(f"\n\ngenerate headings for {clause_id} attempt {attempt}")
        print(f"{prompt}\n\n")
        print(response)
    
    def _write_to_cache(self, cache_file: str, clause_id: str, headings: List[str]) -> None:
        """Write headings to cache file.
        
        Args:
            cache_file: File path to write to
            clause_id: ID of the clause
            headings: Heading alternatives to write
        """
        try:
            with open(cache_file, "a") as store:
                store.write(f"# {clause_id}\n")
                for heading in headings:
                    store.write(f"{heading}\n")
                store.write("\n\n")
        except IOError as e:
            logger.warning(f"Failed to write cache: {e}")
