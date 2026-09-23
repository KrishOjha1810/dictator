"""The dictation app's identity must not be its own binary hash.

An ad-hoc signature makes macOS identify the app by cdhash, so every rebuild
revokes Microphone and Accessibility while leaving the checkbox in System
Settings switched on. Nothing about that is visible: the app is there, the
toggle is on, and the key does nothing. It cost a real user a confusing
install, so it gets a test.
"""
import subprocess
from unittest import mock

import pytest

from dictator import always, signing


def _requirement():
    r = subprocess.run(["codesign", "-d", "-r-", str(always.APP)],
                       capture_output=True, text=True)
    return r.stdout + r.stderr


@pytest.mark.skipif(not always.APP.exists(), reason="app not built here")
def test_identity_is_the_certificate_not_the_binary():
    req = _requirement()
    assert "designated" in req, f"app is not signed at all: {req!r}"
    assert "cdhash" not in req, (
        "app is ad-hoc signed, so rebuilding it will silently revoke the "
        f"user's permissions: {req.strip()!r}")
    assert "certificate leaf" in req, req.strip()


def test_search_list_keeps_what_is_already_there():
    """Adding our keychain must not evict the user's login keychain.

    security list-keychains -s REPLACES the list rather than appending to it,
    so getting this wrong locks the user out of every password they have
    stored, which is a far worse bug than the one being fixed."""
    login = "/Users/someone/Library/Keychains/login.keychain-db"
    calls = []

    def fake(args, **kw):
        calls.append(args)
        out = f'    "{login}"\n' if "-s" not in args else ""
        return mock.Mock(returncode=0, stdout=out, stderr="")

    with mock.patch.object(signing, "_run", side_effect=fake):
        assert signing._add_to_search_list()

    setter = [c for c in calls if "-s" in c]
    assert len(setter) == 1, calls
    assert login in setter[0], setter[0]
    assert str(signing.KEYCHAIN) in setter[0], setter[0]


def test_existing_keychain_is_never_regenerated():
    """Making a new certificate would revoke the permissions all over again."""
    with mock.patch.object(signing, "KEYCHAIN", mock.Mock(exists=lambda: True)), \
         mock.patch.object(signing, "PASSFILE", mock.Mock(exists=lambda: True)), \
         mock.patch.object(signing, "_password", return_value="pw"), \
         mock.patch.object(signing, "_run", return_value=mock.Mock(returncode=0, stdout="", stderr="")), \
         mock.patch.object(signing, "_add_to_search_list", return_value=True), \
         mock.patch.object(signing, "_create") as create:
        assert signing.identity() == signing.NAME
    create.assert_not_called()


def test_signing_failure_is_logged_not_swallowed():
    """A silent signing failure is how this bug survived in the first place."""
    with mock.patch.object(signing, "identity", return_value="Some Identity"), \
         mock.patch("subprocess.run",
                    return_value=mock.Mock(returncode=1, stdout="", stderr="no identity found")), \
         mock.patch.object(always.core, "log") as log:
        always._sign(always.APP)
    assert log.called, "signing failed and nothing said so"
    assert "no identity found" in " ".join(str(c) for c in log.call_args_list)


def test_an_empty_keychain_is_rebuilt_rather_than_trusted():
    """The check was whether the keychain FILE existed. On a real machine a
    PKCS12 import failed once, leaving a keychain with nothing in it, and from
    then on every run reported the identity as present, codesign found nothing,
    and the app was silently ad-hoc signed. Permissions never stuck and there
    was no way back short of deleting the file by hand."""
    import inspect
    src = inspect.getsource(signing.identity)
    assert "_has_identity()" in src, \
        "identity() trusts the file again instead of what is inside it"


def test_the_identity_check_signs_something():
    """Every cheaper check lies. find-identity reports zero for a self-signed
    certificate on a keychain where codesign works, and find-certificate finds
    the certificate when the private key never made it in, which is exactly
    what a failed import leaves behind."""
    import ast, inspect
    tree = ast.parse(inspect.getsource(signing._has_identity).lstrip())
    # The code, not the comments: the docstring explains why find-identity is
    # the wrong check, and a plain text search fails on that explanation.
    strings = [n.value for n in ast.walk(tree)
               if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    body = " ".join(strings[1:])          # skip the docstring
    assert "codesign" in body, "the identity check no longer tries to sign"
    assert "find-identity" not in body, \
        "back on a check that reports zero for a working keychain"


def test_a_failed_check_does_not_destroy_a_working_keychain():
    """Rebuilding resets every permission the user has granted, so an
    unreadable answer has to mean "leave it alone", not "start again"."""
    from unittest import mock
    with mock.patch.object(signing, "_run", side_effect=OSError("boom")):
        assert signing._has_identity() is True
