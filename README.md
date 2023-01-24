[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

# Telenet Telemeter
[Telenet Telemeter](https://www2.telenet.be/nl/business/klantenservice/raadpleeg-uw-internetverbruik/) Home Assistant custom component. This custom component has been built from the ground up to bring your Telenet internet and mobile phone usage details into Home Assistant to help you towards a better follow up on your usage information. This integration is built against the public website provided by Telenet Belgium and has not been tested for any other countries.

This integration is in no way affiliated with Telenet Belgium.

Some discussion on this topic can be found within the [Home Assistant Forum](https://community.home-assistant.io/t/telenet-telemeter-isp-monthly-data-usage/444810)

Based on source code of [Killian Meersman](https://github.com/KillianMeersman/telemeter), all credits go to him. I've only encapsulated it into a HA HACS Custom Component. 
<p align="right"><img src="https://github.com/myTselection/telenet_telemeter/blob/main/logo.png" width="128"/></p>
<!-- <p align="center"><img src="https://github.com/myTselection/telenet_telemeter/blob/main/Gauge%20Card%20Configuration.png"/></p> -->


## Installation
- [HACS](https://hacs.xyz/): add url https://github.com/myTselection/telenet_telemeter as custom repository (HACS > Integration > option: Custom Repositories)
- Restart Home Assistant
- Add 'Telenet Telemeter' integration via HA Settings > 'Devices and Services' > 'Integrations'
- Provide Telenet username and password
- A sensor Telenet Telemeter should become available with the percentage of data left and extra attributes on usage and period start/end etc.
  - For users having a FUP 'unlimited' data, your actual 'peak' data usage versus the [service limit](https://www2.telenet.be/content/www-telenet-be/nl/klantenservice/wat-is-telenet-netwerkbeheer.html) (eg 750GB/3TB) will be used in order to calculate your overal 'usage' status, so you can denote if you are close to be switched into a limited/smallband mode.
- If 'Mobile' has been selected during setup of the integration, a Telenet telemeter mobile sensor will be created for each mobile subscription. If you have shared data in between subscriptions, a shared sensor will be created as well. For now, the sensor state will show the usage (%) state of the data part of each subscription. But details of data/text/voice volume and usage are added as attributes on the sensor, so this information is available too. 

## Status
Still some optimisations are planned, see [Issues](https://github.com/myTselection/telenet_telemeter/issues) section in GitHub.

## Technical pointers
The main logic and API connection related code can be found within source code telenet_telemeter/custom_components/telenet_telemeter:
- [sensor.py](https://github.com/myTselection/telenet_telemeter/blob/main/custom_components/telenet_telemeter/sensor.py)
- [utils.py](https://github.com/myTselection/telenet_telemeter/blob/main/custom_components/telenet_telemeter/utils.py) -> mainly TelenetSession class

All other files just contain boilerplat code for the integration to work wtihin HA or to have some constants/strings/translations.

## Example usage:
### Gauge & Markdown
```
type: vertical-stack
cards:
  - type: markdown
    content: >
      <img src="https://raw.githubusercontent.com/myTselection/telenet_telemeter/main/logo.png" width="30"/>  **Telenet Telemeter**
      ### Total used:
      {{state_attr('sensor.telenet_telemeter','used_percentage')}}%
      ({{(((state_attr('sensor.telenet_telemeter','includedvolume_usage') or 0) + (state_attr('sensor.telenet_telemeter','extendedvolume_usage') or 0) + (state_attr('sensor.telenet_telemeter','wifree_usage') or 0) + (state_attr('sensor.telenet_telemeter','peak_usage') or 0)/1024/1024)|int}}GB
      of {{state_attr('sensor.telenet_telemeter','total_volume')|int}}GB)
      #### {{state_attr('sensor.telenet_telemeter','period_days_left')|int}} days remaining
      Period {{state_attr('sensor.telenet_telemeter','period_start') |
      as_timestamp | timestamp_custom("%d-%m-%Y")}} -
      {{state_attr('sensor.telenet_telemeter','period_end') | as_timestamp | timestamp_custom("%d-%m-%Y")}} 
      Wi-Free usage: {{(state_attr('sensor.telenet_telemeter','wifree_usage')/1024 )| int}}MB
      {{state_attr('sensor.telenet_telemeter','product')}}, last update:
      *{{state_attr('sensor.telenet_telemeter','last update') | as_timestamp | timestamp_custom("%d-%m-%Y")}}*
  - type: gauge
    entity: sensor.telenet_telemeter
    max: 100
    min: 0
    needle: true
    unit: '%'
    name: ''
    severity:
      green: 0
      yellow: 60
      red: 80
```
<p align="center"><img src="https://github.com/myTselection/telenet_telemeter/blob/main/Markdown%20Gauge%20Card%20example.png"/></p>

### Example conditional card:
A conditional card might be desired to show a warning when high data used and many days are left. For such a conditional card, an extra binary sensor can be defined in `configuration.yml` 
If data used_percentage (data used %) is bigger than the period_used_percentage (time % in current period) and data used_percentage is higher than 70% 
```
binary_sensor:
  - platform: template
    sensors:
      telenet_warning:
        friendly_name: Telenet Warning
        value_template: >
           {{state_attr('sensor.telenet_telemeter','used_percentage') > state_attr('sensor.telenet_telemeter','period_used_percentage') and state_attr('sensor.telenet_telemeter','used_percentage') > 70}}
```
This binary sensor can than be used in a conditional lovelace card. The info will only be shown in case you risk to be put on small band soon. Example:
```   
type: conditional
conditions:
  - entity: binary_sensor.telenet_warning
    state: 'on'
card:
  type: markdown
  content: >-
    Total used:
    **{{state_attr('sensor.telenet_telemeter','used_percentage')}}%**
    ({{(((state_attr('sensor.telenet_telemeter','includedvolume_usage') or 0) + (state_attr('sensor.telenet_telemeter','extendedvolume_usage') or 0) + (state_attr('sensor.telenet_telemeter','wifree_usage') or 0) + (state_attr('sensor.telenet_telemeter','peak_usage') or 0))/1024/1024)|int}}GB
    of {{state_attr('sensor.telenet_telemeter','total_volume')|int}}GB)
    {{state_attr('sensor.telenet_telemeter','period_days_left')|int}} days remaining
```
