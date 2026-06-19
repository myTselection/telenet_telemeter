[![HACS Default](https://img.shields.io/badge/HACS-Default-blue.svg)](https://github.com/hacs/default)
[![GitHub release](https://img.shields.io/github/release/myTselection/telenet_telemeter.svg)](https://github.com/myTselection/telenet_telemeter/releases)
![GitHub repo size](https://img.shields.io/github/repo-size/myTselection/telenet_telemeter.svg)

[![GitHub issues](https://img.shields.io/github/issues/myTselection/telenet_telemeter.svg)](https://github.com/myTselection/telenet_telemeter/issues)
[![GitHub last commit](https://img.shields.io/github/last-commit/myTselection/telenet_telemeter.svg)](https://github.com/myTselection/telenet_telemeter/commits/main)
[![GitHub commit activity](https://img.shields.io/github/commit-activity/m/myTselection/telenet_telemeter.svg)](https://github.com/myTselection/telenet_telemeter/graphs/commit-activity)

# Telenet / BASE Telemeter Home Assistant Integration

[Telenet Telemeter](https://www2.telenet.be/nl/business/klantenservice/raadpleeg-uw-internetverbruik/) Home Assistant custom component also supporting [BASE Telemeter](https://www.base.be/nl/klantenzone/internet/je-internetverbruik.html). This custom component brings Telenet and BASE internet and mobile usage details into Home Assistant. It is built against the public API used by the Telenet and BASE web apps and has not been tested for other countries.

This integration is in no way affiliated with Telenet Belgium.

| Warning |
| --- |
| Please do not report issues with this integration to Telenet; they will not be able to support it. |

Some discussion on this topic can be found on the [Home Assistant Forum](https://community.home-assistant.io/t/telenet-telemeter-isp-monthly-data-usage/444810).

Originally based on the Python application by [Killian Meersman](https://github.com/KillianMeersman/telemeter).

<p align="left"><img src="./logo.png" width="64"/></p>

## Installation

- [HACS](https://hacs.xyz/): search for **Telenet Telemeter** in HACS integrations and install it.
  - [![Open your Home Assistant instance and open the repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg?style=flat-square)](https://my.home-assistant.io/redirect/hacs_repository/?owner=myTselection&repository=telenet_telemeter&category=integration)
- Restart Home Assistant.
- Add **Telenet Telemeter** from **Settings > Devices & Services > Integrations**.
- Select provider: `Telenet` or `BASE`.
- Provide your username and password.
- Choose whether to track internet usage, mobile usage, or both.
- Telenet Business accounts are not supported.

## Default Entities

The integration uses the Home Assistant device name `Telenet Telemeter` and short entity names. With one account configured, the default generated entity IDs are:

| Entity | Default entity ID |
| --- | --- |
| Internet usage | `sensor.telenet_telemeter_internet_<product_id>` |
| Peak indicator | `sensor.telenet_telemeter_peak_<product_id>` |
| Mobile line usage | `sensor.telenet_telemeter_mobile_<msisdn>` |
| Mobile days left | `sensor.telenet_telemeter_mobile_<msisdn>_days_left` |
| Mobile max data | `sensor.telenet_telemeter_mobile_<msisdn>_max_data` |
| Mobile usage percentage | `sensor.telenet_telemeter_mobile_<msisdn>_usage` |
| Mobile voice used | `sensor.telenet_telemeter_mobile_<msisdn>_voice_used` |
| Mobile last update | `sensor.telenet_telemeter_mobile_<msisdn>_last_update` |
| Announcements | `sensor.telenet_telemeter_announcements` |
| Wi-Fi switch | `switch.telenet_telemeter_wifi_<product_id>` |


## Sensors

### Internet - `sensor.telenet_telemeter_internet_<product_id>`

State: data used in `GB`. For TURBO/FUP plans this is the FUP counter; for CAP plans this is the consumed amount of the allocated cap.

| Attribute | Description | Example |
| --- | --- | --- |
| `usage_gb` | Data used this period | `268.61` |
| `peak_usage_gb` | Peak traffic downloaded in GB | `266.75` |
| `offpeak_usage_gb` | Off-peak traffic downloaded in GB | `805.51` |
| `total_downloaded_gb` | Peak + off-peak total downloaded in GB | `1072.26` |
| `used_percentage` | Percentage of cap used | `27.3` |
| `period_days_left` | Days remaining in billing period | `10.1` |
| `period_next_start` | Date the next period begins | `2026-06-12` |
| `last_update_formatted` | Human-readable last update time | `22:06 on 1 Jun` |
| `period_start` | Period start date/time | `2026-05-12` |
| `period_end` | Period end date/time | `2026-06-11` |
| `period_used_percentage` | Percentage of billing period elapsed | `64.3` |
| `included_volume` | Included volume from product details | `3145728` |
| `extended_volume` | Extended volume from product details | `0` |
| `total_volume` | Total cap in GB | `300` |
| `wifree_usage` | Wi-Free usage | `0` |
| `includedvolume_usage` | Included-volume usage | `268.61` |
| `extendedvolume_usage` | Extended-volume usage | `0` |
| `peak_usage` | Peak usage value | `266.75` |
| `offpeak_usage` | Off-peak usage value | `805.51` |
| `squeezed` | Whether the line is speed-limited | `false` |
| `product` | Product label or label key | `turbo` |
| `download_speed` | Contracted download speed | `1 Gbps` |
| `upload_speed` | Contracted upload speed | `50 Mbps` |
| `modemMac` | Modem MAC address when available | `00:11:22:33:44:55` |
| `wifiEnabled` | Modem Wi-Fi enabled | `true` |
| `wifreeEnabled` | HomeSpot / Wi-Free enabled | `true` |

For FUP / TURBO plans, only peak traffic counts toward the FUP service limit. Off-peak traffic is tracked separately. The sensor state uses the same FUP counter shown by the Telenet app when available.

### Peak Indicator - `sensor.telenet_telemeter_peak_<product_id>`

State indicates whether peak hours are active. Attributes include:

| Attribute | Description |
| --- | --- |
| `peak` | Peak-hours active flag |
| `peak_usage` | Peak usage |
| `offpeak_usage` | Off-peak usage |
| `used_percentage` | Usage percentage |
| `wifree_usage` | Wi-Free usage |
| `squeezed` | Whether the line is speed-limited |
| `servicecategory` | Product service category |
| `download_speed` | Current or contracted download speed |
| `upload_speed` | Current or contracted upload speed |

### Mobile - `sensor.telenet_telemeter_mobile_<msisdn>`

State: mobile data used in `GB`.

| Attribute | Description | Example |
| --- | --- | --- |
| `label` | Mobile plan label | `Mobile Unlimited` |
| `usage_gb` | Data used this period in GB | `64.13` |
| `used_percentage_data` | Data used percentage | `21.4` |
| `max_data_gb` | Data cap this period in GB | `300` |
| `data_unlimited` | Unlimited/FUP data plan flag | `true` |
| `period_days_left` | Days until billing period resets | `10.1` |
| `has_voice` | Whether the line has voice usage | `true` |
| `voice_used_minutes` | Voice minutes used | `50.8` |
| `voice_max_minutes` | Voice cap; `null` can mean unlimited | `null` |
| `voice_unlimited` | Unlimited voice plan flag | `true` |
| `last_update_formatted` | Human-readable last update | `22:06 on 1 Jun` |
| `total_volume_data` | Raw used data string | `64.13 GB` |
| `remaining_volume_data` | Remaining data string | `235.87 GB` |
| `total_volume_text` | Text/SMS usage string | `0 messages` |
| `remaining_volume_text` | Remaining text/SMS string | `unlimited` |
| `total_volume_voice` | Voice usage string | `50.8 minutes` |
| `remaining_volume_voice` | Remaining voice string | `unlimited` |
| `number` | Line number / MSISDN | `0474123456` |
| `mobileinternetonly` | Data-only SIM flag | `false` |
| `active` | Line status | `ACTIVE` |
| `outofbundle` | Raw out-of-bundle value when available | `0 EUR` |
| `outofbundle_eur` | Total out-of-bundle spend this period | `0` |
| `outofbundle_details` | Out-of-bundle breakdown by category | see below |

Out-of-bundle detail keys:

| Key | Description |
| --- | --- |
| `OOB_NATIONAL_VOICE` | Calls to Belgian numbers outside bundle |
| `OOB_INTERNATIONAL_VOICE` | International calls outside bundle |
| `OOB_ROAMING_VOICE` | Roaming voice calls |
| `OOB_NATIONAL_SMS` | National SMS outside bundle |
| `OOB_INTERNATIONAL_SMS` | International SMS |
| `OOB_ROAMING_SMS` | Roaming SMS |
| `OOB_MMS` | MMS messages |
| `OOB_NATIONAL_DATA` | Data outside bundle |
| `OOB_ROAMING_DATA` | Roaming data outside bundle |
| `OOB_PAY_BY_MOBILE_AND_PREMIUM` | Premium / pay-by-mobile charges |

### Mobile Sub-Sensors

For API v2 mobile subscriptions, five additional entities are created automatically for each mobile line:

| Entity name suffix | Entity ID suffix | Unit | Source field |
| --- | --- | --- | --- |
| `days left` | `_days_left` | `days` | `period_days_left` |
| `max data` | `_max_data` | `GB` | `max_data_gb` |
| `usage %` | `_usage` | `%` | `used_percentage_data` |
| `voice used` | `_voice_used` | `min` | `voice_used_minutes` |
| `last update` | `_last_update` | none | `last_update_formatted` |

### Legacy Mobile Entities

For non-v2 API responses, the integration can also create:

| Entity | Default entity ID |
| --- | --- |
| Shared mobile usage | `sensor.telenet_telemeter_mobile_shared_<index>` |
| Assigned mobile line | `sensor.telenet_telemeter_mobile_<number>` |
| Unassigned mobile line | `sensor.telenet_telemeter_mobile_<number>` |

### Announcements - `sensor.telenet_telemeter_announcements`

State: number of unread inbox messages.

| Attribute | Description |
| --- | --- |
| `last_update` | Timestamp when the inbox cache was processed |
| `unread_count` | Number of unread messages |
| `messages` | List of message objects, including ID, title, body, type, date, and read state |

## Switch

### Wi-Fi - `switch.telenet_telemeter_wifi_<product_id>`

Shows and controls whether the modem Wi-Fi is enabled. This entity is created only when internet tracking is enabled and the integration can determine the internet product identifier.

## Service

### `telenet_telemeter.reboot_internet`

Reboots the internet modem. The service is registered only when internet tracking is enabled.

```yaml
service: telenet_telemeter.reboot_internet
data: {}
```

## Technical Pointers

- [sensor.py](https://github.com/myTselection/telenet_telemeter/blob/main/custom_components/telenet_telemeter/sensor.py)
- [switch.py](https://github.com/myTselection/telenet_telemeter/blob/main/custom_components/telenet_telemeter/switch.py)
- [coordinator.py](https://github.com/myTselection/telenet_telemeter/blob/main/custom_components/telenet_telemeter/coordinator.py)
- [utils.py](https://github.com/myTselection/telenet_telemeter/blob/main/custom_components/telenet_telemeter/utils.py) - `TelenetSession` API client

Enable debug logging in `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.telenet_telemeter: debug
```

## Example Dashboard Cards

The examples below use:

- `sensor.telenet_telemeter_internet_w12345678`
- `sensor.telenet_telemeter_mobile_0474123456`

Replace those with your own entity IDs.

### Markdown Card - Internet Usage (TURBO/FUP)

```yaml
type: markdown
content: >-
  ## Internet - {{ state_attr('sensor.telenet_telemeter_internet_w12345678', 'product') }}

  **{{ states('sensor.telenet_telemeter_internet_w12345678') }} GB** used
  (FUP counter - peak only)

  | | |
  |---|---|
  | Peak downloaded | {{ state_attr('sensor.telenet_telemeter_internet_w12345678', 'peak_usage_gb') }} GB |
  | Off-peak downloaded | {{ state_attr('sensor.telenet_telemeter_internet_w12345678', 'offpeak_usage_gb') }} GB |
  | **Total downloaded** | **{{ state_attr('sensor.telenet_telemeter_internet_w12345678', 'total_downloaded_gb') }} GB** |
  | Days left | {{ state_attr('sensor.telenet_telemeter_internet_w12345678', 'period_days_left') }} days |
  | Next period | {{ state_attr('sensor.telenet_telemeter_internet_w12345678', 'period_next_start') }} |
  | Last update | {{ state_attr('sensor.telenet_telemeter_internet_w12345678', 'last_update_formatted') }} |
  | Speed | {{ state_attr('sensor.telenet_telemeter_internet_w12345678', 'download_speed') }} / {{ state_attr('sensor.telenet_telemeter_internet_w12345678', 'upload_speed') }} |
```

### Markdown Card - Mobile Usage

```yaml
type: markdown
content: >-
  ## Mobile - {{ state_attr('sensor.telenet_telemeter_mobile_0474123456', 'label') }}

  **{{ states('sensor.telenet_telemeter_mobile_0474123456') }} GB** used
  of {{ state_attr('sensor.telenet_telemeter_mobile_0474123456', 'max_data_gb') }} GB
  ({{ state_attr('sensor.telenet_telemeter_mobile_0474123456', 'used_percentage_data') }}%)

  | | |
  |---|---|
  | Remaining | {{ state_attr('sensor.telenet_telemeter_mobile_0474123456', 'remaining_volume_data') }} |
  | Voice used | {{ state_attr('sensor.telenet_telemeter_mobile_0474123456', 'voice_used_minutes') }} min |
  | Days left | {{ state_attr('sensor.telenet_telemeter_mobile_0474123456', 'period_days_left') }} days |
  | Last update | {{ state_attr('sensor.telenet_telemeter_mobile_0474123456', 'last_update_formatted') }} |
```

### Gauge & Markdown - Internet (FUP)

Uses the [Dual Gauge Card](https://github.com/custom-cards/dual-gauge-card).

<p align="center"><img src="./examples/Markdown%20Gauge%20Card%20example.png"/></p>

<details><summary>Show code</summary>

```yaml
type: vertical-stack
cards:
  - type: markdown
    content: >-
      ## Internet - {{ state_attr('sensor.telenet_telemeter_internet_w12345678', 'product') }}

      **FUP counter (peak): {{ states('sensor.telenet_telemeter_internet_w12345678') }} GB**

      Peak: {{ state_attr('sensor.telenet_telemeter_internet_w12345678', 'peak_usage_gb') }} GB &nbsp;|&nbsp;
      Off-peak: {{ state_attr('sensor.telenet_telemeter_internet_w12345678', 'offpeak_usage_gb') }} GB &nbsp;|&nbsp;
      Total: {{ state_attr('sensor.telenet_telemeter_internet_w12345678', 'total_downloaded_gb') }} GB

      {{ state_attr('sensor.telenet_telemeter_internet_w12345678', 'period_days_left') | int }} days remaining
      (period ends {{ state_attr('sensor.telenet_telemeter_internet_w12345678', 'period_next_start') }})

      {{ state_attr('sensor.telenet_telemeter_internet_w12345678', 'download_speed') }} / {{ state_attr('sensor.telenet_telemeter_internet_w12345678', 'upload_speed') }}
      - last update: *{{ state_attr('sensor.telenet_telemeter_internet_w12345678', 'last_update_formatted') }}*
  - type: history-graph
    entities:
      - entity: sensor.telenet_telemeter_internet_w12345678
    hours_to_show: 500
    refresh_interval: 60
```

</details>

### ApexCharts Card - Peak vs Off-Peak

Uses the [ApexCharts Card](https://github.com/RomRider/apexcharts-card).

<p align="center"><img src="./examples/ApexChartExample.png"/></p>

<details><summary>Show code</summary>

```yaml
type: custom:apexcharts-card
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
  - entity: sensor.telenet_telemeter_internet_w12345678
    attribute: peak_usage_gb
    name: Peak
    unit: " GB"
    type: column
    color: darkviolet
    group_by:
      func: max
      duration: 1d
    show:
      datalabels: true
  - entity: sensor.telenet_telemeter_internet_w12345678
    attribute: offpeak_usage_gb
    name: Off-peak
    unit: " GB"
    type: column
    color: steelblue
    group_by:
      func: max
      duration: 1d
    show:
      datalabels: true
  - entity: sensor.telenet_telemeter_internet_w12345678
    attribute: total_downloaded_gb
    name: Total downloaded
    unit: " GB"
    type: line
    color: orange
    group_by:
      func: max
      duration: 1d
```

</details>

### Conditional Warning Card

Show a warning when data usage is ahead of the billing period.

<details><summary>Show code</summary>

Add to `configuration.yaml`:

```yaml
binary_sensor:
  - platform: template
    sensors:
      telenet_internet_warning:
        friendly_name: Telenet Internet Warning
        value_template: >
          {{ state_attr('sensor.telenet_telemeter_internet_w12345678', 'used_percentage') | float(0)
             > state_attr('sensor.telenet_telemeter_internet_w12345678', 'period_used_percentage') | float(0)
             and state_attr('sensor.telenet_telemeter_internet_w12345678', 'used_percentage') | float(0) > 70 }}
```

Lovelace conditional card:

```yaml
type: conditional
conditions:
  - entity: binary_sensor.telenet_internet_warning
    state: "on"
card:
  type: markdown
  content: >-
    ⚠️ High internet usage!
    {{ states('sensor.telenet_telemeter_internet_w12345678') }} GB used
    ({{ state_attr('sensor.telenet_telemeter_internet_w12345678', 'used_percentage') }}%)
    with {{ state_attr('sensor.telenet_telemeter_internet_w12345678', 'period_days_left') | int }} days remaining.
```

</details>

## Status

See [Issues](https://github.com/myTselection/telenet_telemeter/issues) for planned improvements.
