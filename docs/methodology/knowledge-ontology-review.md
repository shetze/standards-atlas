# Knowledge ontology review guide

Use the ontology dimension to classify the engineering subject of a clause, not its
normative force or presentation style.

| Knowledge kind | Use when the clause represents |
|---|---|
| `technique` | a reusable engineering technique or analytical approach |
| `measure` | a preventive, detective, mitigating, or assurance measure |
| `method` | a defined way of performing analysis, development, verification, or validation |
| `process` | an organized lifecycle or workflow |
| `artifact` | a required or described work product, record, plan, report, or specification |
| `role` | an actor or organizational role as the subject of the knowledge |
| `evidence` | information used to justify, demonstrate, or assess compliance or safety |
| `concept` | a domain concept without a more specific knowledge kind |

Statement and knowledge classifications may coexist. "The technique is described in..."
can be `description` plus `technique`; "The method shall be applied" can be `requirement`
plus `method`. Do not infer a knowledge kind solely from an annex heading, but use the
heading as context when the clause content supports it.
