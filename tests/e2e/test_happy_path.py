"""Real-browser coverage for the one flow that has to work: sign up, list a
container, see it. Everything before this was found by hand; this is the start
of catching it by machine instead. Add more journeys incrementally rather than
trying to cover everything at once."""

import re

from playwright.sync_api import Page, expect


def test_signup_create_listing_and_view_it(page: Page, live_server_url: str):
    page.goto(f"{live_server_url}/signup")
    page.locator('form[action="/signup"] input[name="email"]').fill("e2e@example.com")
    page.locator('form[action="/signup"] input[name="password"]').fill("correct-horse-battery")
    page.locator('form[action="/signup"] button[type="submit"]').click()

    expect(page).to_have_url(f"{live_server_url}/")

    page.goto(f"{live_server_url}/listings/new")
    page.locator('form[action="/listings"] input[name="title"]').fill("A dozen mason jars")
    page.locator('form[action="/listings"] button[type="submit"]').click()

    expect(page).to_have_url(re.compile(r"/listings/\d+$"))
    expect(page.get_by_text("A dozen mason jars")).to_be_visible()
