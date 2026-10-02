# Access owner-only data

## Sub-features

- Deny an anonymous private request.
- Deny an invalid bearer token.
- Accept the generated synthetic owner token through the real middleware.

## How to get to it (user POV)

An authenticated owner client requests private dashboard data. `GET /api/users` provides a small route for proving that authentication works before extending the driver to other private flows.

## Driving it with verification

```sh
.venv/bin/python3 -m verification verify private-access
```

Expect 401 for anonymous and invalid-token requests. Expect 200 with the synthetic user registry after authentication. The driver generates the credential internally. Do not copy production tokens or personal `users.json` into the fixture or proof.

Sources: [authentication middleware](../../../../../dashboard/auth.py), [auth tests](../../../../../tests/test_auth_middleware.py).

## Gotchas

This scenario proves the private read boundary. It does not exercise owner approval actions, newsletter delivery, social posting, the pipeline-secret path, or dashboard browser login. Those need their own behavior checks and existing task authorization.
