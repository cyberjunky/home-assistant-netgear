# Changelog

## 0.1.1

- **No more "log in again" every few hours:** the switch ends the integration's login session now and then, and can refuse a new login for a short while. That was taken for a wrong password straight away. Now the integration logs in again by itself, tries again with every read, and asks for the password only when the switch has refused the login 10 times in a row (about 5 minutes).

## 0.1.0

- First version: NETGEAR Plus switches in Home Assistant. Per port its link, link speed, traffic in and out and totals; per PoE port on/off, power cycle, power, status, voltage, current, temperature, class and fault; the front panel LEDs; restart; the traffic over the whole switch. The model is found by itself, the switch is known by its serial number, and it can be reconfigured and logged in again. English and Dutch.
