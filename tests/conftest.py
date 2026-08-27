"""Shared pytest setup.

CLAUDE.md: "Tests must not require network access or API keys." Nothing
enforced that, so the rule drifted. On 2026-08-23, with the Fly box degraded,
`TestPhaseSync::test_happy_path` left `warm_public_site` unmocked and sat in
its ten-minute backend wait, and the whole suite hung behind it. A test that
reaches the internet is slow when the internet is fine and a hang when it is
not, and the times you most want to run the suite are the times it is not.

The guard below fails such a test in place, naming the address, instead of
letting it wait. Loopback stays open, because the FastAPI and dashboard tests
talk to a local test server over a real socket.
"""

import socket

import pytest

_real_create_connection = socket.create_connection
_real_socket_connect = socket.socket.connect


def _is_local(address: object) -> bool:
    """True for loopback and for the AF_UNIX paths a local server may use."""
    if isinstance(address, (str, bytes)):
        return True
    if not isinstance(address, tuple) or not address:
        return True
    host = address[0]
    if not isinstance(host, str):
        return True
    return host in {"localhost", "127.0.0.1", "::1", "", "0.0.0.0"} or host.endswith(".local")


def _blocked(address: object) -> pytest.fail.Exception:
    return pytest.fail.Exception(
        f"Test tried to open a network connection to {address!r}. "
        "Tests must not require network access (CLAUDE.md). Patch the client "
        "at its call site, or mock the helper that reaches out."
    )


@pytest.fixture(autouse=True)
def no_outbound_network(monkeypatch):
    """Fail any test that opens a socket to somewhere other than this machine."""

    def guarded_create_connection(address, *args, **kwargs):
        if not _is_local(address):
            raise _blocked(address)
        return _real_create_connection(address, *args, **kwargs)

    def guarded_connect(self, address, *args, **kwargs):
        if not _is_local(address):
            raise _blocked(address)
        return _real_socket_connect(self, address, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


@pytest.fixture(autouse=True)
def _site_cache_off_repo(tmp_path_factory, monkeypatch):
    """Keep the disk response cache out of the repo's real data directory.

    The story and entity handlers persist finished responses under
    DATA_DIR/<user>/site-cache (dashboard/site_cache.py). A test that patches
    api.DATA_DIR gets the real behavior inside its own tmp tree. A test that
    leaves DATA_DIR pointing at the repo's data/ (some hit the handlers
    against the real reports tree) must not write fixture responses there, so
    for exactly that case the root is swapped for a throwaway directory.
    """
    try:
        from dashboard.routes import api as _api
    except Exception:  # dashboard deps missing in a narrow test env
        yield
        return

    repo_data_dir = _api.DATA_DIR
    original_root = _api._site_cache_root
    throwaway: dict[str, object] = {}

    def guarded_root(user):
        if _api.DATA_DIR is not repo_data_dir:
            return original_root(user)
        safe_user = _api._safe_user(user)
        if safe_user is None:
            return None
        if "root" not in throwaway:
            throwaway["root"] = tmp_path_factory.mktemp("site-cache")
        return throwaway["root"] / safe_user

    monkeypatch.setattr(_api, "_site_cache_root", guarded_root)
    yield


@pytest.fixture(autouse=True)
def _clear_api_fingerprint_memos():
    """Reset the public-API fingerprint memos between tests.

    dashboard/routes/api.py memoizes the story-tree fingerprint for 5 seconds
    so a request does not sweep 53 date directories on the event loop. Tests
    that write a file and query it in the same second would otherwise read a
    fingerprint left behind by an earlier test and see a stale cache. Harmless
    in production, where the thing that moves the fingerprint is a daily sync.
    """
    try:
        from dashboard.routes import api as _api
    except Exception:  # dashboard deps missing in a narrow test env
        yield
        return
    _api._reset_fingerprint_cache()
    _api._reset_story_file_index()
    yield
    _api._reset_fingerprint_cache()
    _api._reset_story_file_index()
