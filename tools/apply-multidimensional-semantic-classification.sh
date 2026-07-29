#!/usr/bin/env bash
set -euo pipefail
rm -f src/standards_atlas/domain/model/semantic_role.py \
  src/standards_atlas/application/services/semantic_role_classifier.py \
  src/standards_atlas/application/ports/semantic_role_classifier.py
rm -rf src/standards_atlas/resources/semantic/prompts/semantic-role-classification \
  src/standards_atlas/resources/semantic/tasks/semantic-role-classification
