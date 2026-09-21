<!-- PROJECT SHIELDS -->
[![hacs_badge][hacs-shield]][hacs-url]
![Project Stage][project-stage-shield]

![Project Maintenance][maintenance-shield]
[![Maintainability][maintainability-shield]][maintainability-url]

# OJ Microline Thermostat Integration for Home Assistant

The OJ Microline Thermostat integration allows you to control your
thermostat from Home Assistant.

It has been tested and developed on the following models:

## Supported models

| Model            |
|------------------|
| OWD5             |
| UWG4             |
| WCD5             |

After installation you can add the thermostat through the integration page. Currently setting a preset mode and temperature is supported. Adjusting
the HVAC mode will (re)set it to the schedule preset.

## Requirements

Your thermostat needs to be connected to the internet. For OWD5 model thermostats you will need the API key and customer ID that is used by the app that you currently use to control your thermostat.

## HACS installation

Add this integration using HACS by searching for `OJ Microline Thermostat` on the `Integrations` page.

## Manual installation

Create a directory called `ojmicroline_thermostat` in the `<config directory>/custom_components/` directory on your Home Assistant instance.
Install this integration by copying all files in `/custom_components/ojmicroline_thermostat/` folder from this repo into the new `<config directory>/custom_components/ojmicroline_thermostat/` directory you just created.

## Configuration

[![ha_badge][ha-add-shield]][ha-add-url]

To configure the integration, add it using [Home Assistant integrations][ha-add-url]. This will provide you with a configuration screen where you enter the customer ID, API key, username and password.

If you control your OWD5/MWD5 with the SWATT app, choose **WD5 series (SWATT app)**: the app's API key and customer ID are filled in for you, so you only need your SWATT username and password.

## Live updates (WD5 series)

WD5-series thermostats receive live updates through the same notification service the OJ Microline and SWATT apps use, so changes made on the thermostat or in the app show up in Home Assistant within seconds. While this connection is up, the integration polls only every 5 minutes (for energy usage and as a fallback); when it drops, polling returns to every minute and the connection is retried automatically.

## Services (WD5 series)

| Service | Description |
| --- | --- |
| `ojmicroline_thermostat.set_vacation` | Schedule a vacation from `start_date` (00:00) until `end_date` (00:00, the day normal regulation resumes). If the start date has already begun, vacation mode is activated immediately. |
| `ojmicroline_thermostat.cancel_vacation` | Cancel a scheduled or active vacation. An active vacation returns to schedule or manual mode, whichever was used last. |

Like the apps, these apply to the thermostat's whole group.

```yaml
action: ojmicroline_thermostat.set_vacation
target:
  entity_id: climate.living_room
data:
  start_date: "2026-12-24"
  end_date: "2027-01-02"
```

## Contributing

Please see [CONTRIBUTING](.github/CONTRIBUTING.md) and [CODE_OF_CONDUCT](.github/CODE_OF_CONDUCT.md) for details.

## References & Thanks

- https://community.home-assistant.io/t/mwd5-wifi-thermostat-oj-electronics-microtemp/445601
- https://mdapp.medium.com/the-android-emulator-and-charles-proxy-a-love-story-595c23484e02
- https://github.com/radubacaran/mwd5
- https://github.com/klaasnicolaas
- https://github.com/adamjernst
- https://github.com/ViPeR5000

[maintainability-shield]: https://api.codeclimate.com/v1/badges/d77f7409eb02e331261b/maintainability
[maintainability-url]: https://codeclimate.com/github/robbinjanssen/python-ojmicroline-thermostat
[maintenance-shield]: https://img.shields.io/maintenance/yes/2025.svg
[project-stage-shield]: https://img.shields.io/badge/project%20stage-stable-brightgreen.svg?style=for-the-badge

[hacs-url]: https://github.com/hacs/integration
[hacs-shield]: https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge

[ha-add-url]: https://my.home-assistant.io/redirect/config_flow_start/?domain=ojmicroline_thermostat
[ha-add-shield]: https://my.home-assistant.io/badges/config_flow_start.svg
