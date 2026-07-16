"""Proves the emergency-time query path works with ZERO network.

Blocks all socket creation at the OS-interface level, then runs the full
retrieval path. Any network attempt raises. Run from repo root:
  python device/tests/test_offline.py
(Also try it with wifi actually off — same result.)
"""
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class NetworkBlocked(Exception):
    pass


def _blocked(*args, **kwargs):
    raise NetworkBlocked("emergency-time code path attempted a network call")


# Kill every route to the network before importing anything under test.
socket.socket = _blocked
socket.create_connection = _blocked
socket.getaddrinfo = _blocked

from device import query  # noqa: E402


def main():
    conn = query.connect()
    manifest = query.get_manifest(conn)
    assert manifest["region"] == "bay_area", manifest
    assert manifest["bundle_version"], "manifest missing bundle_version"
    assert manifest["first_aid_freshness"], "manifest missing freshness"

    # Intent router
    assert query.route("where is the nearest shelter") == "shelters"
    assert query.route("cant stop the bleeding") == "first_aid"

    # FTS retrieval hits the right entries, offline
    expected = {
        "cant stop the bleeding": "fa_bleeding_control",
        "he's not breathing what do i do": "fa_cpr_adult",
        "smell gas after the quake": "haz_gas_leak",
        "think my arm is broken": "fa_fracture",
        "shes choking cant breathe": "fa_choking",
        "passed out but is breathing": "fa_recovery_position",
    }
    for q, want in expected.items():
        hits = query.search_first_aid(conn, q, k=3)
        assert hits, f"no hits for {q!r}"
        got = hits[0][0]["id"]
        assert got == want, f"{q!r}: expected {want}, got {got}"

    # Nearest-shelter query, offline
    near = query.nearest_shelters(conn, 37.87, -122.27, k=3)
    assert len(near) == 3
    assert near[0][1]["id"] == "ev_mlk_park_berkeley", near[0][1]["id"]
    assert near[0][0] < 1.0, "downtown Berkeley point should be <1km from MLK park"

    # Rendered output carries the freshness timestamp and draft warning
    text = query.render_entry(query.search_first_aid(conn, "burned my hand", k=1)[0][0], manifest)
    assert "UNVETTED_DRAFT" in text and manifest["first_aid_freshness"] in text

    print("OFFLINE TEST PASSED — full query path ran with all sockets blocked")


if __name__ == "__main__":
    main()
