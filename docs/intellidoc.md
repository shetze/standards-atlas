
# Intellidoc – Adding AI to the standards-atlas

The idea is simple and straightforward: based on the solid structural data provided by the standards-atlas, the actual standards documents can be broken down into meaningful parts that can then be used for further processing.

The current implementation is very rough, but it serves the purpose of giving a first impression of what might be possible for further processing.

## Loading the document structure for several standard documents as provided by standards-atlas

As a starting point, intellidoc loads the structure data from standards-atlas, which consists of a list of clauses with their clause ID, possibly the heading, and a type classifier. This looks something like this:

“TOC;b2f3c75152f67bff9079ab38eac370d8;ISO 26262-6:2018 E.1;Objectives;o”

Standard documents are particularly well suited for identifying the meaningful content blocks because they follow a strict rule for numbering clauses. The standards-atlas contains a complete list of these clauses with their respective numbering, and we can assume that we will find exactly these numbers somewhere in the standard documents. The standards-atlas has permission from the standards organizations to reproduce the headings along with the clause numbering. This provides us with additional information that can be used to more reliably determine the correct location of the start of each clause in the standard documents.

While intellidoc loads the structure data for all structure data sets for the various standards in the “load_content_structure()” method, it creates the internal representation of these documents as domain-specific knowledge databases with document trees built from clauses. When building these trees, text statements about the structural context of each clause are automatically created.

## Parsing standard documents in Markdown format

Based on this structural data, Intellidoc parses the standard documents in the “parse_md_content()” method and tries to break them down into clauses. We have decided to use plain Markdown as the input format for the process.

We assume that the standard documents are primarily available as PDF documents.

There are tools that convert other document formats into Markdown. We will discuss such tools later. For now, we will simply assume that Markdown is available and we won't expect it to be perfect.

The fundamental problem here is that PDF is a layout-oriented document format that mainly deals with all the details of how the document looks and how it can be printed. The actual text content is there, but hidden in the visual design. We assume that the conversion process from PDF to Markdown is more or less flawed and that the resulting Markdown documents are therefore more or less unclear. 

Intellidoc takes these noisy Markdown documents as input and looks for the expected bulleted list in the Markdown headings. 

TODO: We may want to use the linear sequence of these headings to find additional heading lines that were not properly identified when the PDF was converted to Markdown.

TODO: We can also calculate a noise level based on the number of missing/extra headings found in the Markdown document.

Currently, intellidoc issues warnings about missing headings, which then have to be manually looked up in the Markdown document and corrected. It also issues warnings about duplicate headings and mismatched heading text. We can add additional checks to improve the metric calculation.

After the analysis is complete, the markdown content is cut into pieces and loaded into the internal representation of the domain-specific knowledge bases with the document trees, one for each standard series. We also have a flat index of all clauses with the clause ID as the key.

TODO: We should create an appropriate class diagram and a formal description of the data structure and methods.

## First use case: Generation of additional heading text

Users of the standards-atlas would like to have associative text hints for identifying individual clauses that are in the original standard documents without headings. This makes it easier for users to navigate within and between the extensive contents of the standard document series.

In the standard documents, only a fraction of the clauses have headings. Most clauses, especially the clauses that define the actual requirements and objectives, are just numbered paragraphs. To make the structure data of the standards-atlas more meaningful, we would like to add text headings for all clauses that are currently just text paragraphs.

Analogous to the manual copy and paste process for the heading text specified in the table of contents of the standard documents, as performed for the standards-atlas, such additional headings can be created manually. As an open-source project, the standards-atlas can hope for a community of users to take on this task as a collective effort.

However, creating a three-word heading for each numbered section is a daunting task. And in 2024, we have other means of getting the job done: this is a perfect task for AI.

So that's what Intellidoc tries to do: it takes the text of the properly split sections, and if a section doesn't have a text heading, it has an LLM create a three-word heading based on the actual text.

For this purpose, we use Ollama as a means to run LLMs locally.

TODO: We should perhaps try different LLMs and experiment with different prompts to optimize the generation of such headings

For the time being, we use Nomotron as the LLM with a very simple prompt. The result is sufficiently accurate to serve as an associative pointer to the actual meaning of a paragraph.

Nomotron is a 42 GB model and generating each heading takes some time. This is not suitable for real-time interactive use.

Therefore, intellidoc creates these headings as a bulk record that can then be loaded and edited later.

Generating text for headings is not unique. Nemotron therefore generates a list of headings and lets the user select the one that best fits. We support this by saving all suggested headings as alternatives with the clause heading object.

To feed these generated headings back into the standards-atlas, we currently select the last heading offered by Nemotron and use it to create an updated data set as input for the standards-atlas. To distinguish these generated headings from the ones manually extracted from the table of contents, we change the clause type classifier from lower case, as used in the Standard Atlas data structure, to upper case. This allows the Standard Atlas to undo the added generated content and revert to the original set of headings as found in the actual standard documents.

## Second use case: creating summaries for branches

