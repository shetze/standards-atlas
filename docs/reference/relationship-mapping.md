# Standard Clause Relations

One of the goals of the Standards Atlas is to establish meaningful connections between the standard documents of the various domains.

We assume that the models trained using AI/ML can be used to automatically recognize such connections based on recognizable semantic similarity of text passages.

As a granularity for the relationships we are looking for, we assume the subdivision into numbered clauses and sub-clauses that is prescribed for the structure in all standard documents according to part 2 of the ISO/IEC directive. We speak of all these numbered components as “clauses”, regardless of the depth of their nesting. We also speak of parent and sibling relationships.

The clauses are divided into normative and informative elements based on their function. 

Normative provisions can be formulated, among other things, as statements, recommendations or requirements. 
Informative elements can be, among other things, terms and definitions and descriptions of methods and techniques.
If obvious, we have marked clauses with these type classification in the standards-atlas data strucuctures which build the ground truth for the slicing of standard documents into clauses.

To determine the relationship between the standard documents at the level of the numbered clauses, we first vectorize the clauses using an embedding model (ingestion) and then use the same model to determine the best matches for each clause of a domain for the other domains (retrieval).

When developing specific methods for determining the semantic relationships between the clauses of different standard domains, an evaluation of the results is necessary but difficult to obtain. The motivation for the project is based on the realization that it is not possible with reasonable effort to determine equivalents in other domains for all clauses. It is also not to be expected that there are equivalents at all for all clauses of a domain. After all, all domains obviously have their own specific features and requirements, which legitimize the formulation of separate standards for functional safety. It should therefore be clear that we do not claim that the Standards Atlas is the be-all and end-all. Nevertheless, relationships should be found and presented as a practical tool for orientation or at least as an offer or associative incentive for finding new solutions in a confusing problem area.

## KPIs

We have identified three indicators that we use to evaluate the quality of the relationships found on the basis of measurable criteria:

### Level 1: Self-identification
The actual task is to find semantically meaningful connections from a clause in a standard domain to clauses in another domain. We expect a method for determining such connections to reliably map each clause to itself if we look for the connection not in another domain but simply in its own domain. Ideally, we expect that the method will identify the same clause as the best match in its own domain for 100% of all clauses. Because we are not performing a lexical comparison of texts, but rather a semantic comparison of content, we have to accept a certain degree of fuzziness in the mapping. In practice, it also happens that different clauses have exactly the same content. For example, there are clauses that are listed but deliberately left blank. This is another reason why we cannot achieve a 100% success rate in self-identification. Therefore, an absolute number for achieving this quality criterion cannot be given. However, the higher the better.

### Level 2: Clusters of siblings
The structure of standard documents is neither random nor arbitrary. The sub-clauses of any clause always have a semantic relationship or similarities. This makes the relationship between siblings and parents in the hierarchy of clauses useful for recognizing relationships between clauses in different domains. We expect that a high-quality method not only connects individual clauses in isolation, but also finds clusters of siblings that then show the semantic context on both sides. How many such clusters are identified and how large these clusters are can therefore be used as a second criterion for the quality of the relationships found. Again, the more and the larger the better.

### Level 3: Reciprocity
We assume that high-quality or semantically strong relationships between clauses from different standard domains work the same way in both directions. We therefore expect that for each strong relationship in one direction, a similarly strong connection will be found in the other direction. Again, we cannot expect a 100% success rate, and the same applies to this criterion: the more the better.

## Implementation Choices

For the implementation of the relationship mapping method, we had to mach choices and we have made a couple of more or less arbitrary decisions. With some trial and error we have improved the methods according to the KPIs described above. 

The following list enumerates some of these decisions, which may or may not be the best possible choice:

1. We use the nomic-embed-text model for the embedding.
2. For the embedding of the clauses in an AI model, we use the nltk sentence tokenizer.
3. We weight the individual sentences based on the self-reference of clauses determined by significance
4. In retrieval, we only look for connections for sentences that have an above-average significance.
5. For these sentences, the retrieval starts with the 10 best matches.
6. If identifiable, we use the a clause type to evaluate the relationship with clauses of the same function more highly in the set of matches found.
7. We ignore clauses that do not recognize themselves as the best match.
8. We are using ollama as the local model service.
9. We are using LlamaIndex as framework for implementation

The actual implementation is very raw and we do not claim truth or usability or anything like that. It is just a proof of concept and a starting point for discussion, new experimentation and future development.


