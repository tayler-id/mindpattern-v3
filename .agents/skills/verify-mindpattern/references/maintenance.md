# Maintain the MindPattern feature map

Update the map when a user entry point, observable behavior, required fixture, or driver command changes. Use the installed `pstack:maintain-verification-skill` when a broader source audit is requested.

1. Run `.venv/bin/python3 -m verification features` and open the affected feature file.
2. Trace its current route, command, and response through source. Check its existing tests.
3. Update the map's entry points, proof, and coverage limits. Keep unsupported behavior visible.
4. If the CLI needs to drive a new path, add a synthetic fixture and assertions through the actual app. Extend its supported requests only after checking path isolation and external calls.
5. Run the changed scenario and relevant regression tests. Inspect the evidence after cleanup.
6. Update the README index if the feature was added, renamed, or removed. Resolve every local link and confirm that the CLI registry points to the right file.

Do not generate claims of complete coverage from an endpoint list. A feature can have multiple entry points, empty and rejected states, persistence, or a browser interaction that the API fixture does not exercise.
