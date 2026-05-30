<div align="center">

<img src="https://raw.githubusercontent.com/kegelmeier/ha-enbw/main/custom_components/enbw/brand/logo.png" alt="EnBW Charging Stations" width="180">

# EnBW Charging Stations

Home Assistant integration to monitor the availability of
**[EnBW](https://www.enbw.com)** electric vehicle charging stations.

[![HACS Custom][hacs-shield]][hacs]
[![GitHub Release][release-shield]][releases]
[![License][license-shield]][license]
![HA Min Version][ha-shield]

[![Open in HACS][hacs-repo-badge]][hacs-repo]

</div>

Polls EnBW's public charging-station API and exposes per-station availability,
per-charger status, and connector details as Home Assistant entities — so you
can automate around whether a charge point is free.

## ✨ Features

- Real-time charging station availability monitoring
- Per-charger status (Available / Occupied / Out of Service)
- Station search by location or manual station ID entry
- Multiple station support
- Configurable polling interval (30–300 seconds)
- German and English translations
- Connector details (plug type, power, cable attached)

## 🔌 Entities

For each station, the integration creates:

| Entity | Type | Description |
|---|---|---|
| Available chargers | Sensor | Number of currently available charge points |
| Total chargers | Sensor | Total number of charge points at the station |
| Available | Binary Sensor | ON when at least one charger is available |
| Charger N | Sensor | Status of individual charge point (AVAILABLE/OCCUPIED/OUT_OF_SERVICE) |
| Charger N power | Sensor | Max power (kW) of individual charge point |

## 📦 Installation

### HACS (recommended)

1. Make sure [HACS](https://hacs.xyz) is installed.
2. Add this repository as a **custom repository** (category **Integration**):

   [![Open in HACS][hacs-repo-badge]][hacs-repo]

   …or in HACS go to **⋮ → Custom repositories**, paste
   `https://github.com/kegelmeier/ha-enbw`, choose **Integration**, and add it.
3. Search for **EnBW Charging Stations**, install, and **restart Home Assistant**.

### Manual

1. Copy `custom_components/enbw/` into your `config/custom_components/` directory.
2. Restart Home Assistant.

## ⚙️ Configuration

After installing, add the integration:

[![Add Integration][config-flow-badge]][config-flow]

…or go to **Settings → Devices & Services → Add Integration → “EnBW Charging Stations”**.

### Getting your API key

The integration uses EnBW's public API, which requires a subscription key:

1. Open the [EnBW charging station map](https://www.enbw.com/elektromobilitaet/produkte/mobilityplus-app/ladestation-finden/map)
2. Open your browser's Developer Tools (F12)
3. Go to the **Network** tab
4. Search for requests to `enbw-emp.azure-api.net`
5. Find the `Ocp-Apim-Subscription-Key` header value — this is your API key

### Adding a station

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **EnBW Charging Stations**
3. Choose either:
   - **Enter station ID manually** — if you know the station ID
   - **Search by location** — to find nearby stations by coordinates
4. Enter your API key
5. The integration validates the connection and adds the station

### Options

After setup, adjust the polling interval via **Configure** on the integration card.

## 🤖 Example automation

Notify when a charger becomes available:

```yaml
automation:
  - alias: "EnBW charger available"
    trigger:
      - platform: state
        entity_id: binary_sensor.enbw_available
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "Charger Available!"
          message: "A charging point is now available at {{ state_attr('binary_sensor.enbw_available', 'address') }}"
```

## 🙏 Credits

Inspired by the [Home Assistant community thread](https://community.home-assistant.io/t/status-of-enbw-charging-stations/409573)
on EnBW charging station monitoring.

## ⚠️ Disclaimer

This is an unofficial, community-built integration. It is **not affiliated with,
endorsed by, or supported by EnBW Energie Baden-Württemberg AG**. “EnBW” is a
trademark of its respective owner. Use at your own risk.

## 📄 License

Released under the [MIT License](LICENSE).

<!-- badges -->
[hacs]: https://hacs.xyz
[hacs-shield]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge
[releases]: https://github.com/kegelmeier/ha-enbw/releases
[release-shield]: https://img.shields.io/github/v/release/kegelmeier/ha-enbw?style=for-the-badge
[license]: https://github.com/kegelmeier/ha-enbw/blob/main/LICENSE
[license-shield]: https://img.shields.io/github/license/kegelmeier/ha-enbw?style=for-the-badge
[ha-shield]: https://img.shields.io/badge/Home%20Assistant-2024.1%2B-41BDF5.svg?style=for-the-badge&logo=home-assistant&logoColor=white
[hacs-repo]: https://my.home-assistant.io/redirect/hacs_repository/?owner=kegelmeier&repository=ha-enbw&category=integration
[hacs-repo-badge]: https://my.home-assistant.io/badges/hacs_repository.svg
[config-flow]: https://my.home-assistant.io/redirect/config_flow_start/?domain=enbw
[config-flow-badge]: https://my.home-assistant.io/badges/config_flow_start.svg
