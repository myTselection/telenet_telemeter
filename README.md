[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

# Telenet Telemeter (Beta)
[Telenet Telemeter](https://www2.telenet.be/nl/business/klantenservice/raadpleeg-uw-internetverbruik/) Home Assistant custom component
discussion [Home Assistant Forum](https://community.home-assistant.io/t/telenet-telemeter-isp-monthly-data-usage/444810)

Based on source code of [Killian Meersman](https://github.com/KillianMeersman/telemeter), all credits go to him. I've only encapsulated it into a HA HACS Custom Component. 
<p align="right"><img src="https://github.com/myTselection/telenet_telemeter/blob/main/logo.png" width="128"/></p>
<!-- <p align="center"><img src="https://github.com/myTselection/telenet_telemeter/blob/main/Gauge%20Card%20Configuration.png"/></p> -->


## Installation
- [HACS](https://hacs.xyz/): add url https://github.com/myTselection/telenet_telemeter as custom repository (HACS > Integration > option: Custom Repositories)
- Restart Home Assistant
- Add 'Telenet Telemeter' integration via HA Settings > 'Devices and Services' > 'Integrations'
- Provide Telenet username and password
- A sensor Telenet Telemeter should become available with the percentage of data left and extra attributes on usage and period start/end etc.

## TODO
- Add logo
- Support mobile usage in separate sensor
- Add 'reload' option
- Register repo as standard HACS repo

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
      ({{((state_attr('sensor.telenet_telemeter','includedvolume_usage')+state_attr('sensor.telenet_telemeter','extendedvolume_usage'))/1024/1024)|int}}GB
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
If a conditional card is desired to show a warning when high data used and many days are left. For such a conditional card, an extra binary sensor can be defined in `configuration.yml` 
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
This binary sensor can than be used in a conditional lovelace card, example:
```
type: conditional
conditions:
  - entity: binary_sensor.telenet_warning
    state: 'On'
card:
  type: markdown
  content: >-
    Total used:
    **{{state_attr('sensor.telenet_telemeter','used_percentage')}}%**
    ({{(state_attr('sensor.telenet_telemeter','includedvolume_usage')/1024/1024)|int}}GB
    of {{state_attr('sensor.telenet_telemeter','total_volume')|int}}GB)
    {{state_attr('sensor.telenet_telemeter','period_days_left')|int}} days remaining
```
