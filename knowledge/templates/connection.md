---
type: connection
from: {{ from_concept }}
to: {{ to_concept }}
strength: {{ strength }}
last_updated: {{ last_updated }}
---

# {{ from_title }} <-> {{ to_title }}

## Relationship

{{ description }}

## Shared Evidence

{% for ev in shared_evidence %}
- [[daily/{{ ev.date }}|{{ ev.title }}]]
{% endfor %}

## From Concept

- [[concepts/{{ from_concept }}]]

## To Concept

- [[concepts/{{ to_concept }}]]
