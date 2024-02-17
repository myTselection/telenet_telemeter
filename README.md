[![HACS Default](https://img.shields.io/badge/HACS-Default-blue.svg)](https://github.com/hacs/default)
[![GitHub release](https://img.shields.io/github/release/myTselection/telenet_telemeter.svg)](https://github.com/myTselection/telenet_telemeter/releases)
![GitHub repo size](https://img.shields.io/github/repo-size/myTselection/telenet_telemeter.svg)

[![GitHub issues](https://img.shields.io/github/issues/myTselection/telenet_telemeter.svg)](https://github.com/myTselection/telenet_telemeter/issues)
[![GitHub last commit](https://img.shields.io/github/last-commit/myTselection/telenet_telemeter.svg)](https://github.com/myTselection/telenet_telemeter/commits/main)
[![GitHub commit activity](https://img.shields.io/github/commit-activity/m/myTselection/telenet_telemeter.svg)](https://github.com/myTselection/telenet_telemeter/graphs/commit-activity)

# Telenet Telemeter Home Assistant integration
[Telenet Telemeter](https://www2.telenet.be/nl/business/klantenservice/raadpleeg-uw-internetverbruik/) Home Assistant custom component. This custom component has been built from the ground up to bring your Telenet internet and mobile phone usage details into Home Assistant to help you towards a better follow up on your usage information. This integration is built against the public website provided by Telenet Belgium and has not been tested for any other countries.

This integration is in no way affiliated with Telenet Belgium. **Please don't report issues with this integration to Telenet**, they will not be able to support you.

Some discussion on this topic can be found within the [Home Assistant Forum](https://community.home-assistant.io/t/telenet-telemeter-isp-monthly-data-usage/444810)

Based on python application of [Killian Meersman](https://github.com/KillianMeersman/telemeter).
<p align="right"><img src="https://github.com/myTselection/telenet_telemeter/blob/main/logo.png" width="128"/></p>
<!-- <p align="center"><img src="https://github.com/myTselection/telenet_telemeter/blob/main/Gauge%20Card%20Configuration.png"/></p> -->


## Installation
- [HACS](https://hacs.xyz/): search for Telenet Telemeter in HACS integrations and install
  - [![Open your Home Assistant instance and open the repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg?style=flat-square)](https://my.home-assistant.io/redirect/hacs_repository/?owner=myTselection&repository=telenet_telemeter&category=integration)
- Restart Home Assistant
- Add 'Telenet Telemeter' integration via HA Settings > 'Devices and Services' > 'Integrations'
- Provide Telenet username and password
- A sensor `sensor.telenet_telemeter_internet_[w123456]` should become available with the percentage of data left and extra attributes on usage and period start/end etc.
  - For users having a FUP 'unlimited' data, your actual 'peak' data usage versus the [service limit](https://www2.telenet.be/content/www-telenet-be/nl/klantenservice/wat-is-telenet-netwerkbeheer.html) (eg 750GB/3TB) will be used in order to calculate your overal 'usage' status, so you can denote if you are close to be switched into a limited/smallband mode.
  - Unlimited (FUP) users should use `peak_usage` and `offpeak_usage` attributes, limited (CAP) users should use `includedvolume_usage` attribute.
  - Depending of new Telenet backend, the value can be in GB or in bytes, so might be needed to divide or multipled twice by 1024 
  - A `sensor.telenet_telemeter_peak_[w123456]` sensor is available indicating if peak time is currently active or not and if all allowed peaktime data has been used, the calculated spead limits will be shown as an attribute
- Switch `switch.telenet_telemeter_wifi` will be added to show the status of the Telenet router wifi. The wifi can be enabled/disabled with this switch.
- If 'Mobile' has been selected during setup of the integration, a Telenet telemeter mobile sensor will be created for each mobile subscription. For now, the sensor state will show the usage (%) state of the data part of each subscription. But details of data/text/voice volume and usage are added as attributes on the sensor, so this information is available too. 
- Service `telenet_telemeter.reboot_internet` will become availabe if internet is enabled. When calling this service, the internet modem will be rebooted.
  <details><summary>Example:</summary>

    ```
    service: telenet_telemeter.reboot_internet
    data: {}
    ```

  </details>

## Status
Still some optimisations are planned, see [Issues](https://github.com/myTselection/telenet_telemeter/issues) section in GitHub.

## Technical pointers
The main logic and API connection related code can be found within source code telenet_telemeter/custom_components/telenet_telemeter:
- [sensor.py](https://github.com/myTselection/telenet_telemeter/blob/main/custom_components/telenet_telemeter/sensor.py)
- [utils.py](https://github.com/myTselection/telenet_telemeter/blob/main/custom_components/telenet_telemeter/utils.py) -> mainly TelenetSession class

All other files just contain boilerplat code for the integration to work wtihin HA or to have some constants/strings/translations.

If you would encounter some issues with this custom component, you can enable extra debug logging by adding below into your `configuration.yaml`:
```
logger:
  default: info
  logs:
     custom_components.telenet_telemeter: debug
```

## Example usage:
### Gauge & Markdown using [dual gauge card](https://github.com/custom-cards/dual-gauge-card)
<p align="center"><img src="https://github.com/myTselection/telenet_telemeter/blob/main/Markdown%20Gauge%20Card%20example.png"/></p>

<details><summary>Show markdown code example</summary>

```
type: vertical-stack
cards:
  - type: markdown
    content: >-
      ## <img
      src="https://raw.githubusercontent.com/myTselection/telenet_telemeter/main/logo.png"
      width="30"/>&nbsp;&nbsp;Telenet Telemeter

      ### Total used:
      {{state_attr('sensor.telenet_telemeter_internet_w123456','used_percentage')}}%
      ({{((((state_attr('sensor.telenet_telemeter_internet_w123456','peak_usage')*1024*1024) or 0) +(state_attr('sensor.telenet_telemeter_internet_w123456','includedvolume_usage') or 0)+(state_attr('sensor.telenet_telemeter_internet_w123456','extendedvolume_usage') or 0))/1024/1024)|int}}GB
      of {{state_attr('sensor.telenet_telemeter_internet_w123456','total_volume')|int}}GB)

      #### {{state_attr('sensor.telenet_telemeter_internet_w123456','period_days_left')|int}}
      days remaining
      ({{state_attr('sensor.telenet_telemeter_internet_w123456','total_volume')|int -
      ((((state_attr('sensor.telenet_telemeter_internet_w123456','peak_usage')*1024*1024) or 0)+(state_attr('sensor.telenet_telemeter_internet_w123456','includedvolume_usage') or 0)+(state_attr('sensor.telenet_telemeter_internet_w123456','extendedvolume_usage') or 0))/1024/1024)|int}}GB)


      Period {{state_attr('sensor.telenet_telemeter_internet_w123456','period_start') |
      as_timestamp | timestamp_custom("%d-%m-%Y")}} -
      {{state_attr('sensor.telenet_telemeter_internet_w123456','period_end') | as_timestamp |
      timestamp_custom("%d-%m-%Y")}} 

      {{state_attr('sensor.telenet_telemeter_internet_w123456','product')}}: {{state_attr('sensor.telenet_telemeter_internet_w123456','download_speed')}}/{{state_attr('sensor.telenet_telemeter_internet_w123456','upload_speed')}} (Peak {{states('sensor.telenet_telemeter_peak_w123456')}}, {{state_attr('sensor.telenet_telemeter_peak_w123456','download_speed')}})

      Laatste update:
      *{{state_attr('sensor.telenet_telemeter_internet_w123456','last update') | as_timestamp |
      timestamp_custom("%d-%m-%Y %H:%M")}}*
  - type: custom:dual-gauge-card
    title: false
    min: 0
    max: 100
    shadeInner: true
    cardwidth: 350
    outer:
      entity: sensor.telenet_telemeter_internet_w123456
      attribute: used_percentage
      label: used
      min: 0
      max: 100
      unit: '%'
      colors:
        - color: var(--label-badge-green)
          value: 0
        - color: var(--label-badge-yellow)
          value: 60
        - color: var(--label-badge-red)
          value: 80
    inner:
      entity: sensor.telenet_telemeter_internet_w123456
      label: period
      attribute: period_used_percentage
      min: 0
      max: 100
      unit: '%'
  - type: history-graph
    entities:
      - entity: sensor.telenet_telemeter_internet_w123456
    hours_to_show: 500
    refresh_interval: 60
```
</details>

### [Apex Chart Card](https://github.com/RomRider/apexcharts-card)
<p align="center"><img src="https://github.com/myTselection/telenet_telemeter/blob/main/ApexChartExample.png"/></p>

<details><summary>Show Apex Chart markdown code example</summary>

```
  - type: custom:apexcharts-card
    apex_config:
      chart:
        stacked: true
      xaxis:
        labels:
          format: dd
      legend:
        show: true
    graph_span: 7d1s
    span:
      end: day
    show:
      last_updated: true
    header:
      show: true
      show_states: true
      colorize_states: true
    series:
      - entity: sensor.telenet_telemeter_peak_w123456
        attribute: peak_usage
        name: Peak
        unit: ' GB'
        type: column
        color: darkviolet
        group_by:
          func: max
          duration: 1d
        show:
          datalabels: true
        transform: return x;
      - entity: sensor.telenet_telemeter_peak_w123456
        attribute: offpeak_usage
        name: Offpeak
        unit: ' GB'
        type: column
        group_by:
          func: max
          duration: 1d
        show:
          datalabels: true
        transform: return x;
```

</details>

### Example conditional card:
A conditional card might be desired to show a warning when high data used and many days are left. For such a conditional card, an extra binary sensor can be defined in `configuration.yml` 
If data `used_percentage` (data used %) is bigger than the `period_used_percentage` (time % in current period) and data `used_percentage` is higher than a chosen percentage (eg 70%)
<details><summary>Show code example</summary>

```
binary_sensor:
  - platform: template
    sensors:
      telenet_warning:
        friendly_name: Telenet Warning
        value_template: >
           {{state_attr('sensor.telenet_telemeter_internet_w123456','used_percentage') > state_attr('sensor.telenet_telemeter_internet_w123456','period_used_percentage') and state_attr('sensor.telenet_telemeter_internet_w123456','used_percentage') > 70}}
```
</details>

This binary sensor can than be used in a conditional lovelace card. The info will only be shown in case you risk to be put on small band soon.
<details><summary>Show code example</summary>

```   
type: conditional
conditions:
  - entity: binary_sensor.telenet_warning
    state: 'on'
card:
  type: markdown
  content: >-
    Total used:
    **{{state_attr('sensor.telenet_telemeter_internet_w123456','used_percentage')}}%**
    ({{(((state_attr('sensor.telenet_telemeter_internet_w123456','includedvolume_usage') or 0) + (state_attr('sensor.telenet_telemeter_internet_w123456','extendedvolume_usage') or 0) + (state_attr('sensor.telenet_telemeter_internet_w123456','peak_usage') or 0))/1024/1024)|int}}GB
    of {{state_attr('sensor.telenet_telemeter_internet_w123456','total_volume')|int}}GB)
    {{state_attr('sensor.telenet_telemeter_internet_w123456','period_days_left')|int}} days remaining
```
</details>
