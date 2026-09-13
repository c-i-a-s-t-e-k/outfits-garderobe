"""A new owner-scoped view is under the privacy contracts, or the suite is red.

Nobody has to remember to write a two-user test: every guarded project route
must have an entry in `tests/owner_scoped_routes.py`, and every scenario in
this folder and in `foreign_id_writes/` parametrizes over that registry.
"""

from tests.owner_scoped_routes import ROUTES, is_guarded, project_routes


def _label(route):
    return route.name or f'{route.route} (unnamed)'


def test_every_guarded_project_route_is_registered():
    unregistered = sorted(
        _label(route)
        for route in project_routes()
        if is_guarded(route.callback) and route.name not in ROUTES
    )

    assert not unregistered, (
        f'Guarded routes missing from tests/owner_scoped_routes.py: {unregistered}. '
        'Register each (name it if it has no name) so the privacy contracts cover it.'
    )


def test_no_registered_route_opts_out_of_login():
    opted_out = sorted(
        route.name
        for route in project_routes()
        if route.name in ROUTES and not is_guarded(route.callback)
    )

    assert not opted_out, (
        f'Registered owner-scoped routes marked @login_not_required: {opted_out}. '
        'An owner-scoped view must never be reachable anonymously.'
    )


def test_every_registered_name_is_a_project_route():
    names = {route.name for route in project_routes()}
    stale = sorted(set(ROUTES) - names)

    assert not stale, (
        f'Registry entries that no project route reverses to: {stale}. '
        'Rename or remove them in tests/owner_scoped_routes.py.'
    )
