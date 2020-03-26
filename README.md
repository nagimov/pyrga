# pyrga

[![PyPI version](https://badge.fury.io/py/pyrga.png)](https://badge.fury.io/py/pyrga)

`pyrga` is a Python 3 library for communicating with [SRS RGA (Residual Gas Analyzer from Stanford Research Systems)](https://www.thinksrs.com/products/rga.html). If you're reading this, you probably know what it is.

## DISCLAIMER

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## WARNINGS

- Read the [license](LICENSE) before using the code.
- Always make sure that you have good vacuum before turning on the filament.
- Think twice before pushing a button. Your RGA is an expensive piece of equipment.
- Follow required safety precautions. Your life is quite valuable too.
- This software comes with no warranties of any kind whatsoever, and may not be useful for anything. Use it at your own risk.

## What is RGA

RGA, or Residual Gas Analyzer is a spectrometer that allows measuring chemical composition of gases present in a low-pressure environment. RGA ionizes various components of the gas mixture creating ions, accelerates and mass-filters ions based on their mass-to-charge ratio and measures these ion currents effectively determining partial pressures of various gases. See [Standford Research Systems](https://www.thinksrs.com/products/rga.html) page for more info, datasheets and user manuals.

## Purpose of this library

This library is an attempt to put together a minimal set of self-explanatory functions to allow single mass measurements and spectrum scans (histograms are not supported). It is built with as many sanity checks as I could think of. **That doesn't mean that you should use this library without reading the manual and understanding principles of RGA operation.**

Most of the functionality is spread over a dozen of getters and setters, making this python library look and feel like Java. This is partly due to specifics of RGA communication protocol, and partly due to my poor taste.

## Why not just use the official app?

While official RGA app from SRS is well built and time tested, I found these limitations to be a show stopper for my applications:

- windows only
- no API (RS232 communication protocol **is** the API)
- when running in "pressure vs time" mode for a few weeks, GUI gets slow and unresponsive

Some of our RGAs run 24/7 for nine months per year, and the official app isn't ideal for such applications.

![Cyclotron RGA](/img/cyclotron_rga.png)

## Installation

Use the package manager [pip](https://pip.pypa.io/en/stable/) to install `pyrga`.

```bash
python3 -m pip install pyrga
```

## Usage

### Single mass scan

```python
import pyrga

if __name__ == "__main__":
    # initialize client with non-default noise floor setting
    RGA = pyrga.RGAClient("/dev/ttyUSB0", noise_floor=0)
    # check filament status and turn it on if necessary
    if not RGA.get_filament_status():
        RGA.turn_on_filament()
    # read partial pressures of air constituent
    MASSES = {
        18: "H2O",
        28: "N2",
        32: "O2",
        40: "Ar",
    }
    for m, i in MASSES.items():
        print("partial pressure of element {} is {} Torr".format(i, RGA.read_mass(m)))
```

output:
```
INFO:pyrga.driver:Opening serial interface /dev/ttyUSB0...
INFO:pyrga.driver:Querying device ID...
INFO:pyrga.driver:Connected to RGA model SRSRGA100 on port /dev/ttyUSB0, id SRSRGA100...
INFO:pyrga.driver:Querying CDEM presence...
INFO:pyrga.driver:Querying filament status...
INFO:pyrga.driver:Querying filament current...
INFO:pyrga.driver:Setting CEDM voltage to 0...
INFO:pyrga.driver:Querying CDEM voltage...
INFO:pyrga.driver:Setting electron energy to default...
INFO:pyrga.driver:Querying electron energy...
INFO:pyrga.driver:Setting ion energy to default...
INFO:pyrga.driver:Setting focus plate voltage to default...
INFO:pyrga.driver:Querying focus plate voltage...
INFO:pyrga.driver:Setting emission current to default...
INFO:pyrga.driver:Setting noise floor to 0... (0 - max averaging, 7 - min averaging)
INFO:pyrga.driver:Querying noise floor setting...
INFO:pyrga.driver:Setting partial pressure sensitivity factor to default...
INFO:pyrga.driver:Querying partial pressure sensitivity factor stored in RGA...
INFO:pyrga.driver:Setting total pressure sensitivity factor to default...
INFO:pyrga.driver:Querying total pressure sensitivity factor stored in RGA...
INFO:pyrga.driver:Zeroing ion detector and applying temperature compensation factors...
INFO:pyrga.driver:Querying filament status...
INFO:pyrga.driver:Querying filament current...
INFO:pyrga.driver:Reading a single scan of amu mass number 18
partial pressure of element H2O is 1.0502660300136425e-07 Torr
INFO:pyrga.driver:Reading a single scan of amu mass number 28
partial pressure of element N2 is 8.462960436562073e-08 Torr
INFO:pyrga.driver:Reading a single scan of amu mass number 32
partial pressure of element O2 is 1.6347885402455663e-08 Torr
INFO:pyrga.driver:Reading a single scan of amu mass number 40
partial pressure of element Ar is 1.4222373806275579e-09 Torr
```

### Spectrum scan

```python
import logging
import matplotlib.pyplot as plt
import pyrga

# turn off logging
logging.getLogger('pyrga').setLevel(logging.CRITICAL)

if __name__ == "__main__":
    # initialize client with default settings
    RGA = pyrga.RGAClient("/dev/ttyUSB0")
    # check filament status and turn it on if necessary
    if not RGA.get_filament_status():
        RGA.turn_on_filament()
    # read analog scan of 1-50 mass range with max resolution of 25 steps per amu
    masses, pressures, total = RGA.read_spectrum(1, 50, 25)
    plt.plot(masses, pressures)
    plt.yscale('log')
    plt.ylim(1e-9, 1e-6)
    plt.show()
```

output:

![spectrum](/img/spectrum.png)

## API

This can hardly be called "documentation". Use at your own risk.

Note: I use the term "amu" willy-nilly and interchangeably with "mass-to-charge ratio". Yes, I know this is incorrect.

### Public functions

```python
calibrate_all()
turn_on_filament()
turn_off_filament()
read_spectrum(amu_min, amu_max, amu_res)
read_mass(amu)
```

### Public getters/setters

```python
get_device_id()
get_cdem_presence()
set_partial_sens(partial_sens_mA_per_Torr)
get_partial_sens()
set_total_sens(total_sens_mA_per_Torr)
get_total_sens()
set_electron_energy(electron_energy_eV)
get_electron_energy()
set_ion_energy(ion_energy_eV)
get_ion_energy()
set_plate_voltage(plate_voltage_V)
get_plate_voltage()
set_spectrogram_params(amu_min, amu_max, amu_res)
get_spectrogram_params()
# this does not turn on/off the filament, use turn_on_filament() and turn_off_filament()
set_emission_current(emission_current_mA)
get_emission_current()
get_filament_status()
set_cdem_voltage(cedm_voltage_V)
get_cdem_voltage()
set_noise_floor(noise_floor)
get_noise_floor()
```

## Logging

Set the logging level via `setLevel`:

```python
import logging
import pyrga

logging.getLogger('pyrga').setLevel(logging.DEBUG)

if __name__ == '__main__':
    RGA = pyrga.RGAClient('/dev/ttyUSB0')
    ...
```

## Testing?

See [Contributing](#contributing).

## Contributing

Documentation is clearly lacking. Tests are non-existent. Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## See also

[Pyrga, Larnaca](https://en.wikipedia.org/wiki/Pyrga,_Larnaca) is a village in the Larnaca District of Cyprus, located on 4 km east of Kornos.
