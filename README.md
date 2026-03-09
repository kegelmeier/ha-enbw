# EnBW Charging Stations for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration to monitor the availability of [EnBW](https://www.enbw.com) electric vehicle charging stations.

## Features

- Real-time charging station availability monitoring
- Per-charger status (Available / Occupied / Out of Service)
- Station search by location or manual station ID entry
- Multiple station support
- Configurable polling interval (30-300 seconds)
- German and English translations
- Connector details (plug type, power, cable attached)

## Entities

For each station, the integration creates:

| Entity | Type | Description |
|---|---|---|
| Available chargers | Sensor | Number of currently available charge points |
| Total chargers | Sensor | Total number of charge points at the station |
| Available | Binary Sensor | ON when at least one charger is available |
| Charger N | Sensor | Status of individual charge point (AVAILABLE/OCCUPIED/OUT_OF_SERVICE) |
| Charger N power | Sensor | Max power (kW) of individual charge point |

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu > **Custom repositories**
3. Add this repository URL and select **Integration** as the category
4. Search for "EnBW Charging Stations" and install
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/enbw` folder to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

### Getting Your API Key

The integration uses EnBW's public API, which requires a subscription key:

1. Open the [EnBW charging station map](https://www.enbw.com/elektromobilitaet/produkte/mobilityplus-app/ladestation-finden/map)
2. Open your browser's Developer Tools (F12)
3. Go to the **Network** tab
4. Search for requests to `enbw-emp.azure-api.net`
5. Find the `Ocp-Apim-Subscription-Key` header value - this is your API key

### Adding a Station

1. Go to **Settings** > **Devices & Services** > **Add Integration**
2. Search for "EnBW Charging Stations"
3. Choose either:
   - **Enter station ID manually** - if you know the station ID
   - **Search by location** - to find nearby stations by coordinates
4. Enter your API key
5. The integration will validate the connection and add the station

### Options

After setup, you can adjust the polling interval via **Configure** on the integration card.

## Example Automations

### Notify when a charger becomes available

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

## Credits

Inspired by the [Home Assistant community thread](https://community.home-assistant.io/t/status-of-enbw-charging-stations/409573) on EnBW charging station monitoring.
