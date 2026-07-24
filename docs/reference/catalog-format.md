# Catalog format

The catalog is YAML with a declared version and collections for knowledge domains, industry sectors, standard families, and profiles.

A family defines its logical key, metadata, physical source documents, AtlasData path, composition behavior, and relationships. A physical source identifies its PDF path, document key, part, publication metadata, and optional content selection.

Content selection supports inclusive page ranges, excluded ranges, and explicit page lists. Positive selection is preferred for alternating bilingual pages because it makes the retained source set unambiguous.

Profiles reference family keys. Relationship targets must exist. Validation rejects duplicate keys, inconsistent part metadata, unresolved references, and unsupported selection combinations.

Use the checked-in `catalogs/standards.yaml` as the executable schema example and run `catalog validate` after every edit.
