import html

import pytest
from django.contrib.auth.models import Permission

import dynamic_configs
from dynamic_configs.models import Config

pytestmark = pytest.mark.django_db

URL = "/admin/dynamic_configs/config/"
FORM = {"allow_null": "", "description": ""}


@pytest.fixture(params=["ConfigHistoryAdmin", "own admin"])
def history_admin(request, settings):
    """Run the test through ConfigHistoryAdmin, and through a project's own ConfigAdminMixin + SimpleHistoryAdmin."""
    if request.param == "own admin":
        settings.ROOT_URLCONF = "tests.contrib.simple_history.urls"


def version_url(name, history_id=None):
    """The address of a config's first version, or of the version ``history_id``."""
    if history_id is None:
        history_id = Config.history.filter(name=name).earliest("history_date", "history_id").history_id
    return f"{URL}{name}/history/{history_id}/"


def staff(client, django_user_model, *codenames):
    """Log ``client`` in as a staff user with only these permissions on configs."""
    user = django_user_model.objects.create_user("staff", password="unused", is_staff=True)
    add_permissions(user, *codenames)
    client.force_login(user)
    return user


def add_permissions(user, *codenames):
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(content_type__app_label="dynamic_configs", codename=codename))


def page_text(response):
    return html.unescape(response.content.decode())


def renamed():
    dynamic_configs.get_or_create("SITE_NAME", "str", "Example")
    dynamic_configs.update("SITE_NAME", "Renamed")


@pytest.mark.usefixtures("history_admin")
def test_a_view_only_user_cant_restore_a_version(client, django_user_model):
    renamed()
    staff(client, django_user_model, "view_config")
    response = client.post(version_url("SITE_NAME"), {**FORM, "value": "Changed"})
    assert response.status_code == 403
    assert Config.objects.get(name="SITE_NAME").value == "Renamed"


@pytest.mark.usefixtures("history_admin")
def test_view_only_user_still_sees_a_past_version(client, django_user_model):
    renamed()
    staff(client, django_user_model, "view_config")
    assert client.get(version_url("SITE_NAME")).status_code == 200


@pytest.mark.usefixtures("history_admin")
def test_a_user_with_change_permission_can_revert(client, django_user_model):
    renamed()
    staff(client, django_user_model, "change_config")
    response = client.post(version_url("SITE_NAME"), {**FORM, "value": "Example"})
    assert response.status_code == 302
    assert Config.objects.get(name="SITE_NAME").value == "Example"


@pytest.mark.usefixtures("history_admin")
def test_revert_is_refused_when_revert_is_disabled(admin_client, settings):
    renamed()
    settings.SIMPLE_HISTORY_REVERT_DISABLED = True
    response = admin_client.post(version_url("SITE_NAME"), {**FORM, "value": "Example"})
    assert response.status_code == 403
    assert Config.objects.get(name="SITE_NAME").value == "Renamed"


@pytest.mark.usefixtures("history_admin")
def test_reverting_a_missing_version_is_not_found(admin_client):
    renamed()
    assert admin_client.post(version_url("SITE_NAME", 999), {**FORM, "value": "Example"}).status_code == 404


@pytest.mark.usefixtures("history_admin")
def test_reverting_a_deleted_config_needs_add_permission(client, django_user_model):
    renamed()
    dynamic_configs.delete("SITE_NAME")
    url = version_url("SITE_NAME")
    user = staff(client, django_user_model, "change_config")
    assert client.post(url, {**FORM, "value": "Example"}).status_code == 403
    assert not Config.objects.filter(name="SITE_NAME").exists()
    add_permissions(user, "add_config")
    assert client.post(url, {**FORM, "value": "Example"}).status_code == 302
    assert Config.objects.get(name="SITE_NAME").value == "Example"


@pytest.mark.usefixtures("history_admin")
def test_a_version_with_another_type_isnt_restored(admin_client):
    dynamic_configs.get_or_create("LIMIT", "int", 5)
    dynamic_configs.update("LIMIT", 6)
    # Changed in the database since that version (the admin never changes a type).
    Config.objects.filter(name="LIMIT").update(type="str", value="six")
    response = admin_client.post(version_url("LIMIT"), {**FORM, "value": "5"}, follow=True)
    assert response.redirect_chain == [(f"{URL}LIMIT/history/", 302)]
    assert (
        "This version's type 'int' isn't the config's type 'str', and a config's type never changes, so it wasn't "
        "restored." in page_text(response)
    )
    assert Config.objects.filter(name="LIMIT").values_list("type", "value").get() == ("str", "six")


@pytest.mark.parametrize("deleted", [False, True], ids=["live", "deleted"])
@pytest.mark.usefixtures("history_admin")
def test_a_version_whose_type_isnt_registered_isnt_restored(admin_client, deleted):
    config = Config.objects.create(name="THEME", type="gone", value="dark")
    if deleted:
        config.delete()
    response = admin_client.post(version_url("THEME"), {**FORM, "value": "light"}, follow=True)
    assert response.redirect_chain == [(f"{URL}THEME/history/", 302)]
    assert (
        "This version's type 'gone' isn't registered, so it wasn't restored. Add the type to "
        "DYNAMIC_CONFIGS['TYPES']." in page_text(response)
    )
    rows = Config.objects.filter(name="THEME").values_list("type", "value")
    assert list(rows) == ([] if deleted else [("gone", "dark")])
