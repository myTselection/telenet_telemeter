[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

# telenet_telemeter (Beta)
[Telenet Telemeter](https://www2.telenet.be/nl/business/klantenservice/raadpleeg-uw-internetverbruik/) Home Assistant custom component
discussion [Home Assistant Forum](https://community.home-assistant.io/t/telenet-telemeter-isp-monthly-data-usage/444810)

Based on source code of [Killian Meersman](https://github.com/KillianMeersman/telemeter), all credits go to him. I've only encapsulated it into a HA HACS Custom Component. 
<p align="right"><img src="https://github.com/myTselection/telenet_telemeter/blob/main/logo.png" width="128"/></p>
<p align="center"><img src="https://github.com/myTselection/telenet_telemeter/blob/main/Gauge%20Card%20Configuration.png"/></p>


## Installation
- [HACS](https://hacs.xyz/): add url https://github.com/myTselection/telenet_telemeter as custom repository (HACS > Integration > option: Custom Repositories)
- Restart Home Assistant
- Add 'Telenet Telemeter' integration via HA Settings > 'Devices and Services' > 'Integrations'
- Provide Telenet username and password
- A sensor Telenet Telemeter should become available with the percentage of data left and extra attributes on usage and period start/end etc.

## TODO
- Add logo
- Support mobile usage in separate sensor
- Add decent release numbers
- Add 'reload' option
- Register repo as standard HACS repo
