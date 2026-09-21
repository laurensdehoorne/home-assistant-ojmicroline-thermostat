"""OJMicroline Thermostat platform configuration."""

import logging
from dataclasses import replace
from datetime import date, datetime, timedelta
from time import monotonic
from typing import Any

import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from ojmicroline_thermostat import (
    WD5API,
    OJMicrolineAuthError,
    OJMicrolineError,
    Thermostat,
)
from ojmicroline_thermostat.const import (
    COMFORT_DURATION,
    REGULATION_MANUAL,
    REGULATION_SCHEDULE,
    REGULATION_VACATION,
    WD5_DATETIME_FORMAT,
)
from ojmicroline_thermostat.ojmicroline import SessionOJMicrolineAPI

from .api import api_from_config_entry_data, oj_microline_from_api
from .const import (
    API_TIMEOUT,
    DOMAIN,
    ENERGY_UPDATE_INTERVAL,
    PUSH_ACTION_UPDATE,
    PUSH_UPDATE_INTERVAL,
    REFRESH_COOLDOWN,
    UPDATE_INTERVAL,
)
from .push import WD5PushClient

_LOGGER = logging.getLogger(__name__)


class OJMicrolineDataUpdateCoordinator(DataUpdateCoordinator):
    """Define an object to fetch data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Class to manage fetching OJ Microline data.

        Args:
        ----
            hass: The HomeAssistant instance.
            entry: The ConfigEntry containing the user input.

        """
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
            request_refresh_debouncer=Debouncer(
                hass, _LOGGER, cooldown=REFRESH_COOLDOWN, immediate=True
            ),
        )
        model_api = api_from_config_entry_data(entry.data)
        self._model_api = model_api
        self._energy_updated: float | None = None
        self.wd5_api: WD5API | None = (
            model_api if isinstance(model_api, WD5API) else None
        )
        self.api = oj_microline_from_api(model_api, hass)

    async def _async_update_data(self) -> dict[str, Thermostat]:
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.

        Returns
        -------
            An object containing the serial number as a key, and
            the resource as a value.

        Raises
        ------
            ConfigEntryAuthFailed: An invalid config was ued.
            UpdateFailed: An error occurred when updating the data.

        """
        try:
            async with async_timeout.timeout(API_TIMEOUT):
                thermostats = await self._async_fetch_thermostats()
                return {resource.serial_number: resource for resource in thermostats}

        except OJMicrolineAuthError as error:
            raise ConfigEntryAuthFailed from error

        except OJMicrolineError as error:
            raise UpdateFailed(error) from error

    async def _async_fetch_thermostats(self) -> list[Thermostat]:
        """Fetch the thermostats, reusing recent energy usage where possible.

        The library fetches energy usage for every thermostat on every poll,
        which is one extra request per thermostat. Energy usage changes
        slowly, so only refresh it every ENERGY_UPDATE_INTERVAL.
        """
        api = self._model_api
        if not isinstance(api, SessionOJMicrolineAPI):
            return await self.api.get_thermostats()

        await self.api.login()
        data = await api.request(
            api.get_thermostats_path,
            method="GET",
            params={
                # pylint: disable-next=protected-access
                "sessionid": api._session_id,  # noqa: SLF001
                **api.get_thermostats_params(),
            },
        )
        thermostats = api.parse_thermostats_response(data)

        now = monotonic()
        refresh_energy = (
            self._energy_updated is None
            or now - self._energy_updated >= ENERGY_UPDATE_INTERVAL
        )
        for thermostat in thermostats:
            previous = (self.data or {}).get(thermostat.serial_number)
            if refresh_energy or previous is None:
                thermostat.energy = await api.get_energy_usage(thermostat)
            else:
                thermostat.energy = previous.energy
        if refresh_energy:
            self._energy_updated = now
        return thermostats

    def async_start_push(self, entry: ConfigEntry) -> None:
        """Start receiving push updates (WD5 series only)."""
        if self.wd5_api is None:
            return
        WD5PushClient(
            self.hass,
            async_get_clientsession(self.hass),
            self.wd5_api,
            self._async_handle_push_message,
            self._async_handle_push_connection,
        ).start(entry)

    @callback
    def _async_handle_push_connection(self, connected: bool) -> None:  # noqa: FBT001
        # Polling is still needed for energy usage and as a fallback, but
        # can be much less frequent while push updates are coming in.
        seconds = PUSH_UPDATE_INTERVAL if connected else UPDATE_INTERVAL
        self.update_interval = timedelta(seconds=seconds)
        if connected:
            # Catch up on anything missed while disconnected.
            self.hass.async_create_task(self.async_request_refresh())

    @callback
    def _async_handle_push_message(self, message: dict[str, Any]) -> None:
        _LOGGER.debug(
            "Push message received: %s",
            {
                key: len(value)
                for key, value in message.items()
                if isinstance(value, list)
            },
        )
        if not self.data:
            return

        data = dict(self.data)
        changed = False
        # Group changes (mode, setpoints, schedule) apply to every thermostat
        # in the group; fetch everything again rather than guessing.
        needs_refresh = bool(message.get("Groups"))

        for item in message.get("ThermostatRealTimes") or []:
            current = data.get(item.get("SerialNumber"))
            if current is None:
                continue
            data[current.serial_number] = replace(
                current,
                online=item.get("Online", current.online),
                heating=item.get("Heating", current.heating),
                temperature_room=item.get("RoomTemperature", current.temperature_room),
                temperature_floor=item.get(
                    "FloorTemperature", current.temperature_floor
                ),
                sensor_mode=item.get("SensorAppl", current.sensor_mode),
            )
            changed = True

        for item in message.get("Thermostats") or []:
            current = data.get(item.get("SerialNumber"))
            if current is None or item.get("Action") != PUSH_ACTION_UPDATE:
                # Added or removed thermostat.
                needs_refresh = True
                continue
            try:
                thermostat = Thermostat.from_wd5_json(item)
            except (KeyError, TypeError, ValueError):
                needs_refresh = True
                continue
            thermostat.energy = current.energy
            data[current.serial_number] = thermostat
            changed = True

        if changed:
            # Unlike async_set_updated_data this keeps the polling schedule,
            # so energy usage keeps being refreshed.
            self.data = data
            self.async_update_listeners()
        if needs_refresh:
            self.hass.async_create_task(self.async_request_refresh())

    async def async_set_vacation(
        self,
        thermostat: Thermostat,
        start: date | None,
        end: date | None,
    ) -> None:
        """Enable (start and end given) or disable vacation for a thermostat's group.

        Mirrors the vacation screen of the OJ Microline and SWATT apps: the
        vacation runs from 00:00 on the start date until 00:00 on the end date.
        If the start date has already begun, vacation mode is activated right
        away. When vacation is disabled while active, the thermostat returns to
        schedule or manual mode, whichever was used last.

        Args:
        ----
            thermostat: The thermostat whose group to update.
            start: The first day of the vacation, or None to disable.
            end: The day normal regulation resumes, or None to disable.

        Raises:
        ------
            OJMicrolineError: The API refused the update.

        """
        api = self.wd5_api
        if api is None:
            msg = "Vacation can only be set on WD5-series thermostats."
            raise OJMicrolineError(msg)

        previous_mode = (
            REGULATION_SCHEDULE
            if thermostat.last_primary_mode_is_auto
            else REGULATION_MANUAL
        )
        regulation_mode = thermostat.regulation_mode
        if start is not None and end is not None:
            begin_time = dt_util.start_of_local_day(start)
            end_time = dt_util.start_of_local_day(end)
            if begin_time <= dt_util.now():
                regulation_mode = REGULATION_VACATION
            elif regulation_mode == REGULATION_VACATION:
                regulation_mode = previous_mode
            vacation = {
                "VacationEnabled": True,
                "VacationBeginDay": begin_time.strftime(WD5_DATETIME_FORMAT),
                "VacationEndDay": end_time.strftime(WD5_DATETIME_FORMAT),
            }
        else:
            if regulation_mode == REGULATION_VACATION:
                regulation_mode = previous_mode
            vacation = {"VacationEnabled": False}

        body = api.update_regulation_mode_body(
            thermostat, regulation_mode, None, COMFORT_DURATION
        )
        body["SetGroup"].update(
            vacation,
            # Keep running comfort/boost periods as they are.
            ComfortEndTime=_format(thermostat.comfort_end_time),
            BoostEndTime=_format(thermostat.boost_end_time),
        )

        await self.api.login()
        response = await api.request(
            api.update_regulation_mode_path,
            method="POST",
            # pylint: disable-next=protected-access
            params={"sessionid": api._session_id},  # noqa: SLF001
            body=body,
        )
        if not api.parse_update_regulation_mode_response(response):
            msg = "Unable to set vacation."
            raise OJMicrolineError(msg)


def _format(value: datetime | None) -> str | None:
    return None if value is None else value.strftime(WD5_DATETIME_FORMAT)
