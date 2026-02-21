"""
Uber ride automation via Playwright persistent browser context.

The user signs in manually the first time; cookies persist in the user_data_dir.
All functions are synchronous wrappers that run Playwright in its own thread
to avoid blocking the async event loop.

IMPORTANT: This is inherently fragile -- it depends on Uber's DOM structure.
All selectors are grouped at the top of this file so they can be updated
when Uber changes their UI.
"""

import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from loguru import logger

UBER_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "uber_browser_profile",
)
os.makedirs(UBER_DATA_DIR, exist_ok=True)

UBER_GO_URL = "https://m.uber.com/go/pickup"


# ---------------------------------------------------------------------------
# DOM selectors -- update these when Uber changes their UI
# ---------------------------------------------------------------------------
class S:
    PICKUP_INPUT = 'input[aria-label="Pickup location"]'
    DEST_INPUT = 'input[aria-label="Dropoff location"]'
    SUGGESTION_ITEM = '[data-testid="suggestion-item"], [class*="suggestion"]'
    SEARCH_RESULT = 'li[data-testid], [role="option"]'
    CONFIRM_PICKUP = 'button:has-text("Confirm pickup")'
    RIDE_OPTION_UBERX = '[data-testid="product.8dd94c06-a25b-4a3c-ac32-5b7f2dfe1fbe"], [class*="product"]:has-text("UberX")'
    CHOOSE_UBERX = 'button:has-text("Choose UberX"), button:has-text("Request UberX")'
    REQUEST_RIDE = 'button:has-text("Request"), button:has-text("Confirm")'
    DRIVER_NAME = '[data-testid="driver-name"], [class*="driver"] [class*="name"]'
    VEHICLE_INFO = '[data-testid="vehicle-info"], [class*="vehicle"]'
    LICENSE_PLATE = '[data-testid="license-plate"], [class*="plate"], [class*="license"]'
    ETA_TEXT = '[data-testid="eta"], [class*="eta"], [class*="arriving"]'
    TRIP_STATUS = '[data-testid="trip-status"], [class*="status"]'
    CANCEL_BUTTON = 'button:has-text("Cancel"), button:has-text("Cancel ride")'
    CANCEL_CONFIRM = 'button:has-text("Yes, cancel"), button:has-text("Cancel ride")'
    ADD_STOP_BUTTON = 'button:has-text("Add stop"), button:has-text("Add a stop")'
    ADD_STOP_INPUT = 'input[aria-label="Add a stop"], input[placeholder*="stop"]'


class RideState(Enum):
    IDLE = "idle"
    REQUESTING = "requesting"
    DRIVER_ASSIGNED = "driver_assigned"
    DRIVER_ARRIVING = "driver_arriving"
    TRIP_STARTED = "trip_started"
    TRIP_COMPLETED = "trip_completed"
    CANCELLED = "cancelled"


@dataclass
class UberSession:
    """Tracks the state of the current Uber browser session."""
    browser_context: object = None
    page: object = None
    state: RideState = RideState.IDLE
    driver_name: str = ""
    vehicle_info: str = ""
    license_plate: str = ""
    eta: str = ""
    monitoring_task: Optional[asyncio.Task] = None
    _executor: ThreadPoolExecutor = field(
        default_factory=lambda: ThreadPoolExecutor(max_workers=1)
    )


_session: Optional[UberSession] = None


def _get_session() -> UberSession:
    global _session
    if _session is None:
        _session = UberSession()
    return _session


async def initialize_browser() -> str:
    """Launch or reconnect the Playwright persistent browser.
    Call once at server startup."""
    session = _get_session()
    if session.page is not None:
        return "Uber browser already running."

    try:
        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
        session.browser_context = await pw.chromium.launch_persistent_context(
            user_data_dir=UBER_DATA_DIR,
            headless=False,
            viewport={"width": 430, "height": 932},
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.0 Mobile/15E148 Safari/604.1"
            ),
        )
        pages = session.browser_context.pages
        session.page = pages[0] if pages else await session.browser_context.new_page()

        current = session.page.url
        if "uber.com" not in current:
            await session.page.goto(UBER_GO_URL, timeout=30000)

        logger.info("Uber browser initialized")
        return "Uber browser is ready. Sign in if you haven't already."
    except Exception as e:
        logger.error(f"Failed to initialize Uber browser: {e}")
        return f"Failed to start Uber browser: {e}"


async def _safe_fill(page, selector: str, text: str, timeout: int = 5000) -> bool:
    try:
        el = await page.wait_for_selector(selector, timeout=timeout)
        if el:
            await el.click()
            await el.fill(text)
            return True
    except Exception:
        pass
    return False


async def _safe_click(page, selector: str, timeout: int = 5000) -> bool:
    try:
        el = await page.wait_for_selector(selector, timeout=timeout)
        if el:
            await el.click()
            return True
    except Exception:
        pass
    return False


async def _safe_text(page, selector: str, timeout: int = 3000) -> str:
    try:
        el = await page.wait_for_selector(selector, timeout=timeout)
        if el:
            return (await el.text_content() or "").strip()
    except Exception:
        pass
    return ""


async def _pick_first_suggestion(page) -> bool:
    """Wait for autocomplete suggestions and click the first one."""
    await page.wait_for_timeout(1500)
    for sel in [S.SUGGESTION_ITEM, S.SEARCH_RESULT, "li"]:
        try:
            items = await page.query_selector_all(sel)
            if items:
                await items[0].click()
                await page.wait_for_timeout(800)
                return True
        except Exception:
            continue
    return False


def book_uber(destination: str, pickup: str | None = None) -> str:
    """Book an Uber ride. Runs the async flow on the existing event loop."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            future = asyncio.ensure_future(_book_uber_async(destination, pickup))
            return "Booking Uber... you'll receive SMS updates."
        else:
            return loop.run_until_complete(_book_uber_async(destination, pickup))
    except Exception as e:
        logger.error(f"book_uber error: {e}")
        return f"Failed to book Uber: {e}"


async def _book_uber_async(destination: str, pickup: str | None = None) -> str:
    session = _get_session()
    page = session.page
    if page is None:
        return "Uber browser not initialized. Please start the server first."

    try:
        await page.goto(UBER_GO_URL, timeout=30000)
        await page.wait_for_timeout(2000)

        if pickup:
            filled = await _safe_fill(page, S.PICKUP_INPUT, pickup)
            if filled:
                await _pick_first_suggestion(page)

        filled = await _safe_fill(page, S.DEST_INPUT, destination)
        if not filled:
            return "Could not find the destination input on Uber."
        await _pick_first_suggestion(page)

        await page.wait_for_timeout(2000)

        await _safe_click(page, S.RIDE_OPTION_UBERX, timeout=5000)
        await page.wait_for_timeout(1000)

        for btn_sel in [S.CHOOSE_UBERX, S.REQUEST_RIDE]:
            clicked = await _safe_click(page, btn_sel, timeout=3000)
            if clicked:
                await page.wait_for_timeout(1500)

        session.state = RideState.REQUESTING
        return f"Uber ride to {destination} requested. I'll send you updates as the ride progresses."

    except Exception as e:
        logger.error(f"Uber booking error: {e}")
        return f"Failed to book Uber: {e}"


def uber_status() -> str:
    """Check the current Uber ride status."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            future = asyncio.ensure_future(_uber_status_async())
            return _format_status_sync()
        else:
            return loop.run_until_complete(_uber_status_async())
    except Exception as e:
        return f"Failed to check status: {e}"


def _format_status_sync() -> str:
    session = _get_session()
    parts = [f"Ride status: {session.state.value}"]
    if session.driver_name:
        parts.append(f"Driver: {session.driver_name}")
    if session.vehicle_info:
        parts.append(f"Vehicle: {session.vehicle_info}")
    if session.license_plate:
        parts.append(f"Plate: {session.license_plate}")
    if session.eta:
        parts.append(f"ETA: {session.eta}")
    return "\n".join(parts) if len(parts) > 1 else "No active ride."


async def _uber_status_async() -> str:
    session = _get_session()
    page = session.page
    if page is None:
        return "Uber browser not initialized."

    session.driver_name = await _safe_text(page, S.DRIVER_NAME)
    session.vehicle_info = await _safe_text(page, S.VEHICLE_INFO)
    session.license_plate = await _safe_text(page, S.LICENSE_PLATE)
    session.eta = await _safe_text(page, S.ETA_TEXT)

    status_text = await _safe_text(page, S.TRIP_STATUS)
    if status_text:
        lower = status_text.lower()
        if "arriving" in lower or "on the way" in lower:
            session.state = RideState.DRIVER_ARRIVING
        elif "started" in lower or "in progress" in lower or "trip" in lower:
            session.state = RideState.TRIP_STARTED
        elif "completed" in lower or "rate" in lower:
            session.state = RideState.TRIP_COMPLETED
        elif "assigned" in lower or "meet" in lower:
            session.state = RideState.DRIVER_ASSIGNED

    return _format_status_sync()


def cancel_uber() -> str:
    """Cancel the current Uber ride."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_cancel_uber_async())
            return "Cancelling your Uber ride..."
        else:
            return loop.run_until_complete(_cancel_uber_async())
    except Exception as e:
        return f"Failed to cancel: {e}"


async def _cancel_uber_async() -> str:
    session = _get_session()
    page = session.page
    if page is None:
        return "Uber browser not initialized."

    clicked = await _safe_click(page, S.CANCEL_BUTTON)
    if clicked:
        await page.wait_for_timeout(1000)
        await _safe_click(page, S.CANCEL_CONFIRM, timeout=3000)
        session.state = RideState.CANCELLED
        return "Uber ride cancelled."
    return "Could not find the cancel button. The ride may have already ended."


def add_uber_stop(stop_address: str) -> str:
    """Add a stop to the current Uber ride."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_add_stop_async(stop_address))
            return f"Adding stop: {stop_address}"
        else:
            return loop.run_until_complete(_add_stop_async(stop_address))
    except Exception as e:
        return f"Failed to add stop: {e}"


async def _add_stop_async(stop_address: str) -> str:
    session = _get_session()
    page = session.page
    if page is None:
        return "Uber browser not initialized."

    clicked = await _safe_click(page, S.ADD_STOP_BUTTON)
    if not clicked:
        return "Could not find the 'Add stop' button."

    await page.wait_for_timeout(1000)
    filled = await _safe_fill(page, S.ADD_STOP_INPUT, stop_address)
    if not filled:
        filled = await _safe_fill(page, S.DEST_INPUT, stop_address)
    if not filled:
        return "Could not enter the stop address."

    await _pick_first_suggestion(page)
    return f"Stop added: {stop_address}"


async def start_ride_monitor(send_sms_fn, from_number: str, to_number: str) -> None:
    """Background task that polls the Uber page for ride state changes
    and sends SMS updates via the provided send_sms_fn.

    send_sms_fn(body, from_, to) should send a Twilio SMS.
    """
    session = _get_session()
    prev_state = session.state
    consecutive_errors = 0

    while True:
        try:
            await asyncio.sleep(15)
            await _uber_status_async()

            if session.state == prev_state:
                consecutive_errors = 0
                continue

            prev_state = session.state
            consecutive_errors = 0

            if session.state == RideState.DRIVER_ASSIGNED:
                msg = (
                    f"Your Uber driver is assigned!\n"
                    f"Driver: {session.driver_name or 'N/A'}\n"
                    f"Vehicle: {session.vehicle_info or 'N/A'}\n"
                    f"Plate: {session.license_plate or 'N/A'}\n"
                    f"ETA: {session.eta or 'N/A'}"
                )
                send_sms_fn(msg, from_number, to_number)

            elif session.state == RideState.DRIVER_ARRIVING:
                msg = f"Your Uber driver is arriving! ETA: {session.eta or 'soon'}"
                send_sms_fn(msg, from_number, to_number)

            elif session.state == RideState.TRIP_STARTED:
                msg = "Your Uber trip has started. Have a safe ride!"
                send_sms_fn(msg, from_number, to_number)

            elif session.state in (RideState.TRIP_COMPLETED, RideState.CANCELLED):
                status_word = "completed" if session.state == RideState.TRIP_COMPLETED else "cancelled"
                msg = f"Your Uber trip has been {status_word}."
                send_sms_fn(msg, from_number, to_number)
                break

        except asyncio.CancelledError:
            break
        except Exception as e:
            consecutive_errors += 1
            logger.error(f"Ride monitor error ({consecutive_errors}): {e}")
            if consecutive_errors >= 10:
                logger.error("Too many monitor errors, stopping.")
                break
