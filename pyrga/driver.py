# -*- coding: utf-8 -*-
"""Python client for SRS RGA (Residual Gas Analyzer from Stanford Research Systems)."""

import logging
import struct
import time
import serial


def seq(start, stop, step):
    return [start + step * i for i in range(int(round((stop - start) / step)))] + [stop]


class RGAException(Exception):
    pass


class RGAClient:
    """RGAClient primary client object to communicate with SRS RGA

    The :class:`~.RGAClient` object holds information necessary to connect to SRS RGA via serial interface.
    Requests to read data, set and query parameters can be made to RGA directly through the client.

    :param com_port: serial port to be used for communication with RGA (e.g. '/dev/ttyUSB0' or 'COM4')
    :type com_port: str
    :param partial_sens_mA_per_Torr: partial pressure sensitivity to be used when converting ion current to pressure,
    in units of mA/Torr, defaults to 'default' (value is queried from RGA)
    :type partial_sens_mA_per_Torr: float
    :param total_sens_mA_per_Torr: total pressure sensitivity to be used when converting ion current to pressure,
    in units of mA/Torr, defaults to 'default' (value is queried from RGA)
    :type total_sens_mA_per_Torr: float
    :param electron_energy_eV: electron impact ionization energy in units of eV, limits: [25, 105], defaults to 70
    :type electron_energy_eV: int
    :param ion_energy_eV: energy of ions in the anode grid cage in units of eV, choices: 8 or 12, defaults to 12
    :type ion_energy_eV: int
    :param plate_voltage_V: negative bias voltage of the focus plate in units of V, limits: [0, 150], defaults to 90
    :type plate_voltage_V: int
    :param emission_current_mA: requested electron emission current in units of mA, limits: [0.00, 3.50] with step
    of 0.02, e.g. allowed values: 0.00, 0.02, 0.04... (zero value turns off the filament), defaults to 1.00
    :type emission_current_mA: float
    :param cedm_voltage_V: negative high voltage across the electron multiplier (CDEM) in units of V, this setting only
    works in RGA heads with the CDEM option installed, limits: [0, 2490] (zero value turns off the electron multiplier
    and enables Faraday cup detection), defaults to 0 (Faraday cup detection)
    :type cedm_voltage_V: int
    :param noise_floor: electrometer’s noise-floor, sets the rate and detection limit for ion current measurements,
    lower noise-floor means cleaner baselines and lower detection limits but longer measurement and scanning times,
    limits: [0, 7], defaults to 4
    :type noise_floor: int

    :raises RGAException:
        - if can't communicate with RGA via specified serial port
        - if can't query RGA parameters
        - if any of parameters are of a wrong type or out of bounds
        - if set parameter differs from reported readback value
        - if reported status byte contains active error bits
    """

    _STATUS_ERROR_BITS = [
        "RS232_ERR",
        "FIL_ERR",
        None,
        "CEM_ERR",
        "QMF_ERR",
        "DET_ERR",
        "PS_ERR",
        None,
    ]
    _STATUS_REPORTING_COMMANDS = ["EE", "FL", "IE", "VF", "CA", "HV"]
    _CURRENT_MULTIPLIER = 1e-16
    _ION_ENERGIES_ALLOWED = {8: 0, 12: 1}  # eV: rga
    _ION_ENERGY_DEFAULT = 12  # eV
    _ELECTRON_ENERGY_MIN = 25  # eV
    _ELECTRON_ENERGY_MAX = 105  # eV
    _ELECTRON_ENERGY_DEFAULT = 70  # eV
    _PLATE_VOLTAGE_MIN = 0
    _PLATE_VOLTAGE_MAX = 150  # V
    _PLATE_VOLTAGE_DEFAULT = 90  # V
    _EMISSION_CURRENT_MIN = 0.0
    _EMISSION_CURRENT_MAX = 3.5  # mA
    _EMISSION_CURRENT_INC = 0.02  # mA
    _EMISSION_CURRENTS_ALLOWED = seq(_EMISSION_CURRENT_MIN, _EMISSION_CURRENT_MAX, _EMISSION_CURRENT_INC)
    _EMISSION_CURRENT_DEFAULT = 1.0  # mA
    _CEDM_VOLTAGE_MIN = 10  # V
    _CEDM_VOLTAGE_MAX = 2490  # V
    _CEDM_VOLTAGE_DEFAULT = 1400  # farady cup operation by default
    _NOISE_FLOORS_ALLOWED = [0, 1, 2, 3, 4, 5, 6, 7]  # 0: max averaging (slow), 7: min averaging (fast)
    _NOISE_FLOOR_DEFAULT = 4  # 0: max averaging (slow), 7: min averaging (fast)
    _AMU_SCAN_MIN = 1  # AMU
    _AMU_RES_MIN = 10  # AMU
    _AMU_RES_MAX = 25  # steps per AMU
    _PARTIAL_SENS_MIN = 0.0  # mA/Torr
    _PARTIAL_SENS_MAX = 10.0  # mA/Torr
    _TOTAL_SENS_MIN = 0.0  # mA/Torr
    _TOTAL_SENS_MAX = 100.0  # mA/Torr
    _SRS_RGA_MODELS = ["SRSRGA100", "SRSRGA200", "SRSRGA300"]

    def __init__(
        self,
        com_port,
        partial_sens_mA_per_Torr="default",
        total_sens_mA_per_Torr="default",
        electron_energy_eV="default",
        ion_energy_eV="default",
        plate_voltage_V="default",
        emission_current_mA="default",
        cedm_voltage_V=0,  # 0: set faraday cup operation by default instead of electron multiplier
        noise_floor="default",
    ):
        """Construct a new RGAClient object."""
        self.logger = logging.getLogger(__name__)
        self._com_port = com_port
        self.logger.info("Opening serial interface %s...", self._com_port)
        try:  # TODO: too wide of an exception handler, make sure to be OS aware too (/dev/tty vs COM4)
            self._com_obj = serial.Serial(
                self._com_port, timeout=5, baudrate=28800, rtscts=1, bytesize=8, stopbits=1, parity="N",
            )
        except:
            raise RGAException(
                "Failed to open serial interface %s. Make sure that the following is true:"
                "- correct serial interface is specified;"
                "- correct cable is used;"
                "- RGA is turned on." % self._com_port
            )
        self.logger.debug("Serial interface object is ready: %s", self._com_obj)

        # set model-dependent RGA parameters
        self._set_device_id()
        self.logger.info(
            "Connected to RGA model %s on port %s, id %s", self._device_model, self._com_port, self._device_id,
        )
        self._set_cdem_presence()

        # define filament status
        self._set_filament_status()

        # set adjustable RGA parameters
        self.set_cdem_voltage(cedm_voltage_V)
        self.set_electron_energy(electron_energy_eV)
        self.set_ion_energy(ion_energy_eV)
        self.set_plate_voltage(plate_voltage_V)
        self.set_emission_current(emission_current_mA)  # this setter does NOT turn on the filament
        self.set_noise_floor(noise_floor)
        self.set_partial_sens(partial_sens_mA_per_Torr)
        self.set_total_sens(total_sens_mA_per_Torr)
        self.calibrate_all()

        # empties
        self._amu_min = None
        self._amu_max = None
        self._amu_res = None

    def calibrate_all(self):
        self.logger.info("Zeroing ion detector and applying temperature compensation factors...")
        self._send_command("CA")
        self._flush_buffer()

    def read_spectrum(self, amu_min=1, amu_max=100, amu_res=10):
        self.logger.info(
            "Reading analog scan from %s amu to %s amu with %s steps/amu", amu_min, amu_max, amu_res,
        )
        if not self._filament_status:
            raise RGAException("Filament is off! Turn on filament first!")
        if self._amu_min != amu_min or self._amu_max != amu_max or self._amu_res != amu_res:
            self.set_spectrogram_params(amu_min, amu_max, amu_res)
        spectrum_len = (self._amu_max - self._amu_min) * self._amu_res + 1
        spectrum_bytes = 4 * (spectrum_len + 1)  # final 4 bytes is total pressure
        self._send_command("SC", "1")
        buffer_bytes = self._read_buffer_chunked(spectrum_bytes, 1000)
        return self._decode_spectrum(buffer_bytes)

    def read_mass(self, amu):
        self.logger.info("Reading a single scan of amu mass number %s", amu)
        if not isinstance(amu, int):
            raise RGAException("AMU mass number must be an integer, specified: %s" % amu)
        if amu < self._AMU_SCAN_MIN or amu > self._amu_scan_max:
            raise RGAException(
                "Specified mass is outside of allowed bounds [%s, %s]" % (self._AMU_SCAN_MIN, self._amu_scan_max)
            )
        if not self._filament_status:
            raise RGAException("Filament is off! Turn on filament first!")
        self._send_command("MR", amu)
        return self._current_to_partial_pressure(self._read_buffer_chunked(4, 10))

    def get_device_id(self):
        self.logger.info("Querying device ID...")
        self._send_command("ID", "?")
        return self._read_buffer_line_ascii()

    def _set_device_id(self):
        self._device_id = self.get_device_id()
        for model in self._SRS_RGA_MODELS:
            if model in self._device_id:
                self._device_model = model
                self._amu_scan_max = int(model.replace("SRSRGA", ""))
                return
        raise RGAException("Cannot query device model")

    def _set_cdem_presence(self):
        self._cdem_present = self.get_cdem_presence()

    def get_cdem_presence(self):
        self.logger.info("Querying CDEM presence...")
        self._send_command("EM", "?")
        status_byte = self._read_buffer_chunked(3, 10)[0]  # last two bytes are \n\r
        bin_str = "{:08b}".format(status_byte)
        if bin_str[7] == "1":
            return False
        return True

    def set_partial_sens(self, partial_sens_mA_per_Torr):
        self.logger.info(
            "Setting partial pressure sensitivity factor to %s...", partial_sens_mA_per_Torr,
        )
        if partial_sens_mA_per_Torr == "default":
            self.logger.debug("Default pressure sensitivity factor specified, querying value stored in RGA...")
            self._partial_sens_mA_per_Torr = self.get_partial_sens()
        else:
            if not isinstance(partial_sens_mA_per_Torr, (float, int)):
                raise RGAException(
                    "Partial pressure sensitivity must be an int or float, specified: %s" % partial_sens_mA_per_Torr
                )
            if partial_sens_mA_per_Torr < self._PARTIAL_SENS_MIN or partial_sens_mA_per_Torr > self._PARTIAL_SENS_MAX:
                raise RGAException(
                    "Partial pressure sensitivity setting is ouside of allowed bounds [%s, %s]" %
                    (self._PARTIAL_SENS_MIN, self._PARTIAL_SENS_MAX)
                )
            self._partial_sens_mA_per_Torr = partial_sens_mA_per_Torr

    def get_partial_sens(self):
        self.logger.info("Querying partial pressure sensitivity factor stored in RGA...")
        self._send_command("SP", "?")
        return float(self._read_buffer_line_ascii())

    def set_total_sens(self, total_sens_mA_per_Torr):
        self.logger.info("Setting total pressure sensitivity factor to %s...", total_sens_mA_per_Torr)
        if total_sens_mA_per_Torr == "default":
            self.logger.debug("Default pressure sensitivity factor specified, querying value stored in RGA...")
            self._total_sens_mA_per_Torr = self.get_total_sens()
        else:
            if not isinstance(total_sens_mA_per_Torr, (float, int)):
                raise RGAException(
                    "Total pressure sensitivity must be an integer or float, specified: %s" % total_sens_mA_per_Torr
                )
            if total_sens_mA_per_Torr < self._TOTAL_SENS_MIN or total_sens_mA_per_Torr > self._TOTAL_SENS_MAX:
                raise RGAException(
                    "Total pressure sensitivity setting is ouside of allowed bounds [%s, %s]" %
                    (self._TOTAL_SENS_MIN, self._TOTAL_SENS_MAX)
                )
            self._total_sens_mA_per_Torr = total_sens_mA_per_Torr

    def get_total_sens(self):
        self.logger.info("Querying total pressure sensitivity factor stored in RGA...")
        self._send_command("ST", "?")
        return float(self._read_buffer_line_ascii())

    def set_electron_energy(self, electron_energy_eV):
        self.logger.info("Setting electron energy to %s...", electron_energy_eV)
        if electron_energy_eV == "default":
            self._electron_energy_eV = self._ELECTRON_ENERGY_DEFAULT
            self.logger.debug("Default electron energy specified, setting value: %s eV...", self._electron_energy_eV)
            self._send_command("EE", "*")
        else:
            if not isinstance(electron_energy_eV, int):
                raise RGAException("Electron energy must be an integer, specified: %s" % electron_energy_eV)
            if electron_energy_eV < self._ELECTRON_ENERGY_MIN or electron_energy_eV > self._ELECTRON_ENERGY_MAX:
                raise RGAException(
                    "Electron energy setting is ouside of allowed bounds [%s, %s]" %
                    (self._ELECTRON_ENERGY_MIN, self._ELECTRON_ENERGY_MAX)
                )
            self._electron_energy_eV = electron_energy_eV
            self._send_command("EE", self._electron_energy_eV)
        self.logger.debug("Verifying set parameter...")
        electron_energy_eV_readback = self.get_electron_energy()
        if electron_energy_eV_readback != self._electron_energy_eV:
            raise RGAException(
                "Electron energy setting readback (%s eV) differs from setpoint (%s eV)" %
                (electron_energy_eV_readback, self._electron_energy_eV)
            )

    def get_electron_energy(self):
        self.logger.info("Querying electron energy...")
        self._send_command("EE", "?")
        return int(self._read_buffer_line_ascii())

    def set_ion_energy(self, ion_energy_eV):
        self.logger.info("Setting ion energy to %s...", ion_energy_eV)
        if ion_energy_eV == "default":
            self._ion_energy_eV = self._ION_ENERGY_DEFAULT
            self.logger.debug(
                "Default ion energy specified, setting value: %s eV...", self._ion_energy_eV,
            )
            self._send_command("IE", "*")
        else:
            if ion_energy_eV not in self._ION_ENERGIES_ALLOWED:
                raise RGAException(
                    "Ion energy must be equal to one of allowed values: %s, specified: %s" %
                    (self._ION_ENERGIES_ALLOWED, ion_energy_eV)
                )
            self._ion_energy_eV = ion_energy_eV
            self._send_command("IE", self._ION_ENERGIES_ALLOWED[self._ion_energy_eV])
        self.logger.debug("Verifying set parameter...")
        ion_energy_eV_readback = self.get_ion_energy()
        if ion_energy_eV_readback != self._ion_energy_eV:
            raise RGAException(
                "Ion energy setting readback (%s eV) differs from setpoint (%s eV)" %
                (ion_energy_eV_readback, self._ion_energy_eV)
            )

    def get_ion_energy(self):
        self.logger.debug("Querying ion energy...")
        self._send_command("IE", "?")
        ie = int(self._read_buffer_line_ascii())
        return next(key for key, value in self._ION_ENERGIES_ALLOWED.items() if value == ie)

    def set_plate_voltage(self, plate_voltage_V):
        self.logger.info("Setting focus plate voltage to %s...", plate_voltage_V)
        if plate_voltage_V == "default":
            self._plate_voltage_V = self._PLATE_VOLTAGE_DEFAULT
            self.logger.debug(
                "Default focus plate voltage specified, setting value: %s V...", self._plate_voltage_V,
            )
            self._send_command("VF", "*")
        else:
            if not isinstance(plate_voltage_V, int):
                raise RGAException("Focus plate voltage must be an integer, specified: %s" % plate_voltage_V)
            if plate_voltage_V < self._PLATE_VOLTAGE_MIN or plate_voltage_V > self._PLATE_VOLTAGE_MAX:
                raise RGAException(
                    "Focus plate voltage setting is outside of allowed bounds [%s, %s]" %
                    (self._PLATE_VOLTAGE_MIN, self._PLATE_VOLTAGE_MAX)
                )
            self._plate_voltage_V = plate_voltage_V
            self._send_command("VF", -self._plate_voltage_V)
        self.logger.debug("Verifying set parameter...")
        plate_voltage_V_readback = self.get_plate_voltage()
        if plate_voltage_V_readback != self._plate_voltage_V:
            raise RGAException(
                "Focus plate voltage setting readback (%s V) differs from setpoint (%s V)" %
                (plate_voltage_V_readback, self._plate_voltage_V)
            )

    def get_plate_voltage(self):
        self.logger.info("Querying focus plate voltage...")
        self._send_command("VF", "?")
        return int(self._read_buffer_line_ascii())

    def set_spectrogram_params(self, amu_min, amu_max, amu_res):
        self.logger.debug(
            "Setting spectrogram parameters: min=%s, max=%s, steps=%s", amu_min, amu_max, amu_res,
        )
        for amu in [amu_min, amu_max, amu_res]:
            if not isinstance(amu, int):
                raise RGAException("AMU values and resolution must be an integer, specified: %s" % amu)
        if amu_min < self._AMU_SCAN_MIN or amu_max > self._amu_scan_max:
            raise RGAException(
                "AMU values are outside of allowed bounds [%s, %s], specified: min %s, max %s" %
                (self._AMU_SCAN_MIN, self._amu_scan_max, amu_min, amu_max)
            )
        if amu_min >= amu_max:
            raise RGAException(
                "AMU min value must be lower than AMU max value, specified: min %s, max %s" %
                (amu_min, amu_max)
            )
        if amu_res < self._AMU_RES_MIN or amu_res > self._AMU_RES_MAX:
            raise RGAException(
                "AMU resolution is outside of allowed bounds [%s, %s], specified: %s" %
                (self._AMU_RES_MIN, self._AMU_RES_MAX, amu_res)
            )
        self._amu_min = amu_min
        self._amu_max = amu_max
        self._amu_res = amu_res
        self._send_command("MI", self._amu_min)
        self._send_command("MF", self._amu_max)
        self._send_command("SA", self._amu_res)
        self.logger.debug("Verifying set parameters...")
        (amu_min_readback, amu_max_readback, amu_res_readback,) = self.get_spectrogram_params()
        if amu_min_readback != self._amu_min or amu_max_readback != self._amu_max or amu_res_readback != self._amu_res:
            raise RGAException(
                "Spectrogram parameters readback (%s, %s, %s) differ from setpoints (%s, %s, %s)" %
                (amu_min_readback, amu_max_readback, amu_res_readback, self._amu_min, self._amu_max, self._amu_res)
            )

    def get_spectrogram_params(self):
        self.logger.info("Querying spectrogram parameters...")
        self._send_command("MI", "?")
        mi = int(self._read_buffer_line_ascii())
        self._send_command("MF", "?")
        mf = int(self._read_buffer_line_ascii())
        self._send_command("SA", "?")
        sa = int(self._read_buffer_line_ascii())
        return (mi, mf, sa)

    def set_emission_current(self, emission_current_mA):
        self.logger.info("Setting emission current to %s...", emission_current_mA)
        if emission_current_mA == "default":
            self._emission_current_mA = self._EMISSION_CURRENT_DEFAULT
            self.logger.debug(
                "Default emission current specified, setting value: %s V...", self._emission_current_mA,
            )
        else:
            if not isinstance(emission_current_mA, (float, int)):
                raise RGAException(
                    "Emission current setting must be an integer or float, specified: %s" % emission_current_mA
                )
            if (
                float(emission_current_mA) < self._EMISSION_CURRENT_MIN
                or float(emission_current_mA) > self._EMISSION_CURRENT_MAX
            ):
                raise RGAException(
                    "Emission current setting is ouside of allowed bounds [%s, %s]" %
                    (self._EMISSION_CURRENT_MIN, self._EMISSION_CURRENT_MAX)
                )
            if emission_current_mA not in self._EMISSION_CURRENTS_ALLOWED:
                raise RGAException("Emission current setting must be specified with increment of 0.02 mA")

    def get_emission_current(self):
        self.logger.info("Querying filament current...")
        self._send_command("FL", "?")
        return float(self._read_buffer_line_ascii())

    def _set_filament_status(self):
        self._filament_status = self.get_filament_status()

    def get_filament_status(self):
        self.logger.info("Querying filament status...")
        if self.get_emission_current() < 0.0 + self._EMISSION_CURRENT_INC:
            return False
        return True

    def turn_on_filament(self):
        self.logger.info(
            "Turning on filament with electron emission current %s mA...", self._emission_current_mA,
        )
        self._filament_status = True  # pylint: disable=W0201
        self._send_command("FL", self._emission_current_mA)
        self.logger.debug("Verifying set parameter...")
        emission_current_mA_readback = self.get_emission_current()
        if (
            emission_current_mA_readback < self._emission_current_mA - self._EMISSION_CURRENT_INC
            or emission_current_mA_readback > self._emission_current_mA + self._EMISSION_CURRENT_INC
        ):
            raise RGAException(
                "Emission current setting readback (%s mA) differs from setpoint (%s mA)"
                % emission_current_mA_readback,
                self._emission_current_mA,
            )

    def turn_off_filament(self):
        self.logger.info("Turning off the filament: setting electron emission to 0...")
        self._filament_status = False  # pylint: disable=W0201
        self._send_command("FL", 0.0)
        self.logger.debug("Verifying set parameter...")
        try:
            filament_current_mA = self.get_emission_current()
            if filament_current_mA < 0.0 + self._EMISSION_CURRENT_INC:
                self.logger.info("Filament is confirmed to be off: %s mA", filament_current_mA)
                return True
        except:  # catching all to guarantee delivery of the error message - pylint: disable=W0702
            pass
        error_msg = "Cannot confirm that the filament is off! Turn off RGA before venting the system!"
        self.logger.error(error_msg)
        raise RGAException(error_msg)

    def set_cdem_voltage(self, cedm_voltage_V):
        if not self._cdem_present:
            self.logger.info("No CDEM installed, not setting CDEM voltage")
            return
        self.logger.info("Setting CEDM voltage to %s...", cedm_voltage_V)
        if cedm_voltage_V == "default":
            self._cedm_voltage_V = self._CEDM_VOLTAGE_DEFAULT
            self.logger.debug(
                "Default CDEM voltage specified, setting value: %s V...", self._cedm_voltage_V,
            )
            self._send_command("HV", "*")
        else:
            if cedm_voltage_V == 0:  # Faraday cup detection
                self.logger.debug("Turning off electron multiplier (Faraday cup detection)")
            else:
                if not isinstance(cedm_voltage_V, int):
                    raise RGAException("CDEM voltage must be an integer, specified: %s" % cedm_voltage_V)
                if cedm_voltage_V < self._CEDM_VOLTAGE_MIN or cedm_voltage_V > self._CEDM_VOLTAGE_MAX:
                    raise RGAException(
                        "CDEM voltage setting is outside of allowed bounds [%s, %s]" %
                        (self._CEDM_VOLTAGE_MIN, self._CEDM_VOLTAGE_MAX)
                    )
            self._cedm_voltage_V = cedm_voltage_V
            self._send_command("HV", self._cedm_voltage_V)
        self.logger.debug("Verifying set parameter...")
        cedm_voltage_V_readback = self.get_cdem_voltage()
        if not self._cedm_voltage_V * 0.9 <= cedm_voltage_V_readback <= self._cedm_voltage_V * 1.1:
            raise RGAException(
                "CDEM voltage setting readback (%s V) differs from setpoint (%s V)" %
                (cedm_voltage_V_readback, self._cedm_voltage_V)
            )

    def get_cdem_voltage(self):
        if not self._cdem_present:
            self.logger.info("No CDEM installed, not querying CDEM voltage")
            return False
        self.logger.info("Querying CDEM voltage...")
        self._send_command("HV", "?")
        return int(self._read_buffer_line_ascii())

    def set_noise_floor(self, noise_floor):
        self.logger.info(
            "Setting noise floor to %s... (0 - max averaging, 7 - min averaging)", noise_floor,
        )
        if noise_floor == "default":
            self._noise_floor = self._NOISE_FLOOR_DEFAULT
            self.logger.debug(
                "Default noise floor specified, setting value: %s V...", self._noise_floor,
            )
            self._send_command("NF", "*")
        else:
            if noise_floor not in self._NOISE_FLOORS_ALLOWED:
                raise RGAException(
                    "Noise floor must be equal to one of allowed values: %s, specified: %s"
                    % self._NOISE_FLOORS_ALLOWED,
                    noise_floor,
                )
            self._noise_floor = noise_floor
            self._send_command("NF", self._noise_floor)
        self.logger.debug("Verifying set parameter...")
        noise_floor_readback = self.get_noise_floor()
        if noise_floor_readback != self._noise_floor:
            raise RGAException(
                "Noise floor setting readback (%s) differs from setpoint (%s)" %
                (noise_floor_readback, self._noise_floor)
            )

    def get_noise_floor(self):
        self.logger.info("Querying noise floor setting...")
        self._send_command("NF", "?")
        return int(self._read_buffer_line_ascii())

    def _send_command(self, cmd, value=""):
        full_cmd = "{}{}\r".format(cmd, value)
        self.logger.debug("Sending command '%s'...", full_cmd)
        ret = self._com_obj.write(full_cmd.encode())
        if ret != len(full_cmd):
            raise RGAException("Wrong response from serial interface object")
        if "?" not in full_cmd and cmd in self._STATUS_REPORTING_COMMANDS:
            self._check_status_byte()

    def _check_status_byte(self):
        self.logger.debug("Checking status byte...")
        status_byte = self._read_buffer_chunked(3, 10)[0]  # last two bytes are \n\r
        bin_str = list(map(int, "{:08b}".format(status_byte)))
        if not self._cdem_present:
            bin_str[3] = 0
        for s, e in zip(bin_str, self._STATUS_ERROR_BITS):
            if s == "1" and e:
                raise RGAException("Error %s reported in status echo!" % e)

    def _flush_buffer(self):
        # flush() might not work with USB serial adapters
        self.logger.debug(
            "Flushing buffer, %s bytes read", self._com_obj.read(self._com_obj.in_waiting),
        )

    def _read_buffer_line_ascii(self):
        self.logger.debug("Reading a line from serial port...")
        try:
            buffer_bytes = self._com_obj.readline()  # rely on pyserial timeout
            _ = self._read_buffer_chunked(1)  # reading extra byte required due to \n\r line termination
            buffer_ascii = buffer_bytes.decode("ascii").strip()
        except:
            raise RGAException("Failed to receive buffer line")
        self.logger.debug("Received line from serial port: '%s'", buffer_ascii)
        return buffer_ascii

    def _read_buffer_chunked(self, length_bytes, attempts=10, chunk=64):
        attempt_sleep = 0.5
        recv = 0
        recv_total = 0
        attempt = 0
        self.logger.debug("Waiting for serial buffer to fill up...")
        data_recv = []
        if length_bytes < chunk:
            chunk = length_bytes
        while recv_total < length_bytes:
            while (recv < chunk) and (recv + recv_total != length_bytes):
                attempt += 1
                recv = self._com_obj.in_waiting
                time.sleep(attempt_sleep)
                if attempt > attempts:
                    raise RGAException("Failed to receive buffer")
                self.logger.debug(
                    "%s bytes buffered, %s bytes received, out of %s", recv, recv_total, length_bytes,
                )
            try:
                data_recv.append(self._com_obj.read(recv))
                recv_total += recv
                time.sleep(attempt_sleep)
                recv = self._com_obj.in_waiting
            except:
                raise RGAException("Failed to receive buffer")
        buffer_bytes = b"".join(data_recv)[:length_bytes]
        self.logger.debug("Serial buffer is received: %s", buffer_bytes)
        return buffer_bytes

    def _decode_spectrum(self, spectrum_bytes):
        spectrum_sliced = [spectrum_bytes[i : i + 4] for i in range(0, len(spectrum_bytes), 4)]
        spec_amu = seq(self._amu_min, self._amu_max, 1.0 / self._amu_res)
        spec_amu = list(map(lambda x: round(x, 2), spec_amu))
        spec_pres = list(map(self._current_to_partial_pressure, spectrum_sliced[:-1]))
        if len(spec_amu) != len(spec_pres):
            raise RGAException(
                "Cannot parse spectrum:\n    amu array: %s\n    pressures array: %s" %
                (spec_amu, spec_pres)
            )
        spec_pres_sum = self._current_to_total_pressure(spectrum_sliced[-1])
        return (spec_amu, spec_pres, spec_pres_sum)

    def _decode_bin_current(self, current_bytes):
        """
        Decode binary encoded ion current data from RGA to floating point format in units of A.
        Binary encoding: little-endian integer representing a mantissa with an exponent of 1e-16 units of A.
        """
        try:  # TODO: too wide of an exception handler
            return struct.unpack("<i", current_bytes)[0] * self._CURRENT_MULTIPLIER
        except:
            raise RGAException("Cannot decode binary current value %s" % current_bytes)

    def _current_to_partial_pressure(self, current_bytes):
        return self._decode_bin_current(current_bytes) / self._partial_sens_mA_per_Torr * 1000.0

    def _current_to_total_pressure(self, current_bytes):
        return self._decode_bin_current(current_bytes) / self._total_sens_mA_per_Torr * 1000.0
