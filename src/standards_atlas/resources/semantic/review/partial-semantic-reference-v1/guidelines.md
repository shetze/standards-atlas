# Partial semantic reference review — annotation rules 1.0.0

This is a human reference task, not confirmation of taxonomy authority, a model vote,
or permission to activate a candidate. Review the complete frozen clause, including
notes. Structural context can explain a statement but must not invent absent content.
`unattributed`, `excluded` and `unavailable` facts are not confirmed source authority.
Missing necessary context is a reason to defer, not to guess a negative value.

Review each selected attribute independently. A reviewed Applicability label does not
confirm Statement, Knowledge, Process or Role annotations for the same clause.
Historical/sentinel/model suggestions require an explicit human action in this package;
their original provenance stays separate from that action.

- `primary_function`: principal communicative function. A term can define a process,
  role or technique; definition alone does not make the knowledge subject a concept.
  `statement_functions` includes every supported function, INCLUDING its primary.
- `primary_knowledge_kind`: principal engineering knowledge subject; not communicative
  force or lifecycle contribution. A technique can describe activities without being
  primarily a lifecycle process. `knowledge_kinds` is the complete supported set.
- `process_functions`: independent contributions to a process model: objective,
  prerequisite, input, activity, decision, branch, sequence, output,
  completion_criterion, option or assumption. No knowledge-kind=process gate applies.
  A technique name or a bare heading alone does not establish an activity or objective.
  `primary_process_function`, when selected and non-null, belongs to the complete set.
- `role_semantics_present`: human/organizational responsibility, performance,
  assignment, dependency/independence, consultation, information, participation or
  membership. A name alone is insufficient; a passive role/action statement can be
  present without an explicit actor. `role_relations` contains the supported
  actor/relation_class/target tuples; never invent a missing actor or target.
- `applicability_present`: explicit local statements about normative requirements or
  clauses applying, not applying, or applying only in a stated domain. Technique
  usability/suitability alone is not positive applicability. Carrier clause type is
  not a filter: notes or techniques can contain normative applicability. Conditional
  obligations, references and inherited scope alone do not establish it.

`equals: null`, `equals: false`, and an exact empty set are explicit reviewed values,
not defaults. `equals` checks the complete value/set. `must_include` asserts only a
minimum set and does not exclude other labels. `must_be_empty` asserts an empty
collection, not a missing value. A rejected suggestion without a replacement remains
unresolved. Leave unanswerable attributes deferred, even if other attributes are clear.

Only a complete predeclared selection with required class/stratum coverage can be
published. The holdout-use declaration is a human provenance claim, not software proof
of unseen data. Known Development/Golden/sentinels and equivalent text cannot enter
holdout. Check unrecorded prior use, translations and near-duplicates separately.
