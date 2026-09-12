"""Pin the deploy configuration so a settings regression fails a test, not a deploy.

`manage.py check --deploy` is the list Django keeps of settings that are fine in
development and dangerous in production. Nothing runs it on its own, so this
suite does — the same trick `privatemedia/tests/test_storage_config.py` plays
for media storage.

The assertion cannot be "no issues". The test harness itself trips two of these
checks, for reasons that do not exist in production, and the short-lived HSTS
rollout trips two more on purpose. Both groups are allow-listed by ID below,
each with its reason. Anything else fails.
"""

from django.conf import settings
from django.core.checks import run_checks
from django.test import override_settings

# Issues the harness produces and production does not. Never add an ID here to
# make a real regression pass — fix the setting instead.
HARNESS_ARTIFACTS = {
    # settings_test.py stubs SECRET_KEY with a 38-character placeholder;
    # production's key comes from Railway.
    'security.W009',
    # settings_test.py forces SECURE_SSL_REDIRECT = False, because leaving it on
    # turns every test-client request into a 301 before it reaches a view.
    'security.W008',
}

# Production decisions, not artifacts. These checks only fire once HSTS is on,
# and the HSTS rollout deliberately leaves both flags off: each extends an
# unrecallable browser cache beyond this one host. Revisit together with raising
# SECURE_HSTS_SECONDS.
DELIBERATE_DEVIATIONS = {
    # SECURE_HSTS_INCLUDE_SUBDOMAINS unset.
    'security.W005',
    # SECURE_HSTS_PRELOAD unset.
    'security.W021',
}


def _deploy_check_ids():
    return {message.id for message in run_checks(include_deployment_checks=True)}


def test_deploy_checks_report_nothing_outside_the_allow_list():
    unexpected = _deploy_check_ids() - HARNESS_ARTIFACTS - DELIBERATE_DEVIATIONS

    assert not unexpected, f'check --deploy reports new issues: {sorted(unexpected)}'


def test_hsts_is_enabled_and_not_allow_listed():
    """security.W004 is the debt S-01 discharges; it must never be allow-listed.

    The max-age is deliberately short and without PRELOAD/INCLUDE_SUBDOMAINS —
    a cached HSTS header cannot be recalled. Raising it is a separate decision,
    and this test should change with it, not silently accept it.
    """
    assert 'security.W004' not in HARNESS_ARTIFACTS | DELIBERATE_DEVIATIONS
    assert 'security.W004' not in _deploy_check_ids()
    assert settings.SECURE_HSTS_SECONDS == 3600
    assert not settings.SECURE_HSTS_PRELOAD
    assert not settings.SECURE_HSTS_INCLUDE_SUBDOMAINS


def test_emailed_links_are_https():
    """Without the sites framework, allauth builds mailed URLs from this setting."""
    assert settings.ACCOUNT_DEFAULT_HTTP_PROTOCOL == 'https'


def test_production_email_goes_through_the_brevo_api():
    """Railway Hobby blocks outbound SMTP; an SMTP backend would fail every send.

    pytest-django swaps EMAIL_BACKEND to locmem at test time, so assert against
    the configured ANYMAIL block rather than the live backend.
    """
    assert settings.ANYMAIL['BREVO_API_KEY']
    assert settings.ANYMAIL['REQUESTS_TIMEOUT'] == 10
    assert settings.DEFAULT_FROM_EMAIL


@override_settings(SECURE_SSL_REDIRECT=True)
def test_healthcheck_is_not_redirected_to_https(client):
    """Railway probes /health/ over plain HTTP and fails the deploy on anything but 200.

    settings_test turns SECURE_SSL_REDIRECT off for the rest of the suite, so it
    is switched back on here — otherwise this regression could never show. The
    second assertion proves the redirect really is on for everything else.
    """
    assert client.get('/health/').status_code == 200
    assert client.get('/accounts/login/').status_code == 301
