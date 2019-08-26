import array
import math
import time

import usb.core
import usb.util

from .utils import (
    starts_with,
    most_significant_byte,
    least_significant_byte,
    report_warning,
    to_stdout,
)
from .exceptions import SyncError


class DataLink(object):
    _PAIRING_ID = (8, 8, 8, 8)

    _ENDPOINT_IN = 0x81
    _ENDPOINT_OUT = 0x03

    _FIND_ATTEMPTS = 20
    _PAIR_WRITE_ATTEMPTS = 10
    _PAIR_READ_ATTEMPTS = 5
    _GET_SESSIONS_COUNT_ATTEMPTS = 20
    _GET_SESSION_SIZE_ATTEMPTS = 15
    _GET_SESSION_ATTEMPTS = 20

    # Data length in bytes
    _WRITE_DATA_LENGTH = 256
    _READ_DATA_LENGTH = 512
    _SESSION_PACKET_WITHOUT_HEADER = 446

    _WRITE_TIMEOUT = 1000
    _READ_TIMEOUT = 1000
    _READ_RETRY_TIMEOUT = 2

    _ERROR_TIMEOUT_CODE = 110

    def __init__(self):
        # Hardware ID
        self.hw_id = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.hw_id is not None:
            self._disconnect()

    def synchronize(self):
        self._connect()
        to_stdout("Select 'Connect > Start synchronizing' from your watch\n")

        watch = self._find_watch()
        if watch is None:
            raise SyncError('Watch not found')

        paired = self._pair()
        if not paired:
            raise SyncError('Pairing failed')

    @property
    def sessions(self):
        to_stdout('[sync] Loading training sessions')

        session_count = self._count_sessions()
        if session_count is None:
            raise SyncError('Failed to load training sessions')

        if session_count == 0:
            raise SyncError('No training sessions found')

        session_sizes = []
        for num in range(session_count):
            size = self._read_session_size(num)
            if size is None:
                raise SyncError(f"Can't get a size of session #{num + 1}")

            session_sizes.append(size)

        sessions = []
        for num, size in enumerate(session_sizes):
            session = self._read_session(num, size)
            if session is None:
                report_warning(f"Can't read session #{num + 1}")
                continue

            sessions.append(session)

        return sessions

    def _connect(self):
        self.dev = usb.core.find(idVendor=0x0DA4, idProduct=0x0004)
        if self.dev is None:
            raise SyncError('Polar DataLink not found')

        try:
            # is_kernel_driver_active raises NotImplementedError on Windows
            if self.dev.is_kernel_driver_active(0):
                self.dev.detach_kernel_driver(0)
        except NotImplementedError:
            pass

        self.dev.set_configuration()

        time.sleep(0.4)
        self._write((0x01, 0x07))
        time.sleep(0.001)
        self._write((0x01, 0x40, 0x01, 0x00, 0x51))

    def _disconnect(self):
        self._write((0x01, 0x40, 0x04, 0x00, 0x54, *self.hw_id, 0xB7, 0x00, 0x00, 0x01))

    def _find_watch(self):
        to_stdout('[sync] Looking for the watch')

        for _ in range(self._FIND_ATTEMPTS):
            data = self._read(timeout_sleep=5)
            is_expected_data = self._is_ready(data) and starts_with(
                data, (0x04, 0x42, 0x20)
            )
            if is_expected_data:
                self.hw_id = tuple(reversed(data[5:8]))
                break

            time.sleep(0.001)

        return self.hw_id

    def _pair(self):
        to_stdout('[sync] Pairing with DataLink')

        # Send pairing request PAIR_WRITE_ATTEMPTS times
        for _ in range(self._PAIR_WRITE_ATTEMPTS):
            self._write(
                (
                    0x01,
                    0x40,
                    0x06,
                    0x00,
                    0x54,
                    *self.hw_id,
                    0xB6,
                    0x00,
                    *self._PAIRING_ID,
                )
            )

            data = None
            for _ in range(self._PAIR_READ_ATTEMPTS):
                read_data = self._read(timeout_sleep=0)
                if self._is_ready(read_data):
                    data = read_data
                    break

                time.sleep(0.01)

            # 04:42:03:00:40:b6:00:01 means that the paring
            # has been finished successfully
            if data and data[7] == 0x01:
                return True

            time.sleep(3)

        return False

    def _count_sessions(self):
        send_data = (0x01, 0x40, 0x02, 0x00, 0x54, *self.hw_id)
        self._write(send_data)

        for _ in range(self._GET_SESSIONS_COUNT_ATTEMPTS):
            data = self._read_retry((0x04, 0x42, 0x3C), send_data)
            if data is not None:
                return data[13]

        return None

    def _read_session_size(self, session_number):
        send_data = (
            0x01,
            0x40,
            0x03,
            0x00,
            0x54,
            *self.hw_id,
            0xB2,
            0x00,
            session_number,
        )
        self._write(send_data)

        for _ in range(self._GET_SESSION_SIZE_ATTEMPTS):
            data = self._read_retry((0x04, 0x42, 0x06), send_data)
            if data is not None:
                return (data[8] << 8) + data[7]

            time.sleep(0.001)

        return None

    def _read_session(self, number, size):
        # Session data will come in packets of packet_size size
        packet_size = self._SESSION_PACKET_WITHOUT_HEADER
        packets_count = math.ceil(size / packet_size)
        tail_size = size % packet_size

        session = []
        for packet in range(packets_count):
            is_last = packet + 1 == packets_count
            bytes_received = packet * packet_size
            bytes_to_read = tail_size if is_last and tail_size else packet_size

            send_data = self._assemble_packet_request_data(
                number, bytes_received, bytes_to_read
            )
            self._write(send_data)

            for _ in range(self._GET_SESSION_ATTEMPTS):
                read_data = self._read()
                if self._is_ready(read_data):
                    data = read_data
                    break

                time.sleep(0.01)
            else:
                return None

            session.append(list(data))

        return session

    def _assemble_packet_request_data(
        self, session_number, bytes_received, bytes_to_read
    ):
        return (
            0x01,
            0x40,
            0x09,
            0x00,
            0x54,
            *self.hw_id,
            0xB3,
            0x00,
            session_number,
            least_significant_byte(bytes_received),
            most_significant_byte(bytes_received),
            0x00,
            0x00,
            least_significant_byte(bytes_to_read),
            most_significant_byte(bytes_to_read),
        )

    def _write(self, data):
        data = bytes(data) + bytes(self._WRITE_DATA_LENGTH - len(data))
        return self.dev.write(self._ENDPOINT_OUT, data, self._WRITE_TIMEOUT)

    def _read(self, timeout_sleep=0.5):
        try:
            return self.dev.read(
                self._ENDPOINT_IN, self._READ_DATA_LENGTH, self._READ_TIMEOUT
            )
        except usb.core.USBError as err:
            if err.errno != self._ERROR_TIMEOUT_CODE:
                raise err

        time.sleep(timeout_sleep)
        return array.array('B')

    def _read_retry(self, expected_data, resend_data):
        """Read and retry a request if expected data was not received."""
        data = self._read()
        if self._is_ready(data):
            if starts_with(data, expected_data):
                return data

            time.sleep(self._READ_RETRY_TIMEOUT)
            self._write(resend_data)

        return None

    def _is_ready(self, data):
        """Checks if data is ready to be processed."""
        return len(data) == self._READ_DATA_LENGTH
