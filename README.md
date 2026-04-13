# TermRad 📡⛈️

**Professional Terminal Weather Dashboard**  
_Real-time doppler radar, automated forecasts, and persistent customization in your terminal._

![image](https://github.com/user-attachments/assets/467256d2-9be7-4123-9f9f-2369ac57a2ed)

## Key Features

- **Real-Time Doppler Radar:** Animated Michigan radar loop with location highlighting and meteorological standard color coding.
- **Dynamic Geolocation:** Support for automatic IP-based location detection or manual US Zip Code entry.
- **Persistent Personalization:** Saved user preferences for temperature (F/C), time format (12/24hr), and visual themes.
- **Smart Alerts & Forecast:** Multi-threaded NWS data fetching for real-time alerts and high-performance, freeze-free UI.

## Installation & Setup

### Option 1: System-wide Installation (Recommended)

Install the application as a global command using pip:

```bash
pip install .
termrad
```

### Option 2: Run from Source

If you prefer not to install it system-wide, you can run it directly:

```bash
pip install -r requirements.txt
python3 -m TermRad.app
```

## Usage

- **Normal Mode:** `termrad` or `python3 -m TermRad.app`
- **Unit Tests:** `python3 tests/tests.py`

## Technical Stack

- **UI Framework:** [Textual](https://textual.textualize.io/)
- **Weather Data:** [National Weather Service (NWS) API](https://www.weather.gov/documentation/services-web-api)
- **Geocoding:** [Nominatim (OpenStreetMap)](https://nominatim.org/)
- **Radar Images:** [Iowa Environmental Mesonet (IEM)](https://mesonet.agron.iastate.edu/)
