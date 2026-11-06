"""The admin script on the config admin's own pages, in a real browser."""

from playwright.sync_api import expect


def test_choosing_a_type_moves_on_to_the_value(admin_page):
    admin_page.goto("/admin/dynamic_configs/config/add/")
    admin_page.locator("select[name=type]").select_option("int")
    expect(admin_page).to_have_url("/admin/dynamic_configs/config/add/?type=int")
    expect(admin_page.locator("[name=value]")).to_be_visible()
