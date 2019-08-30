import datetime
import re
from collections import namedtuple
from enum import Enum

import geopy.distance

import polar_rcx5_datalink.utils as utils
from .exceptions import ParserError
from .utils import bcd_to_int


class SampleFields(Enum):
    HR = 'hr'
    LON = 'lon'
    LAT = 'lat'
    DISTANCE = 'distance'
    SPEED = 'speed'
    SATELLITES = 'sat'


class HRType(Enum):
    """Binds type to a byte sequence.

    There is 4 types of HR values defined by a prefix:
    011 -- 8-bit unsigned integer (positive full value)
    10  -- 4-bit unsigned integer (positive delta)
    11  -- 4-bit signed integer (negative delta)
    00  -- 11-bit unsigned integer (positive full value)
    """

    FULL_WITH_PREFIX = '01'
    FULL_PREFIXLESS = '00'
    POS_DELTA = '10'
    NEG_DELTA = '11'


node_fields = [f.value for f in SampleFields if f != SampleFields.SATELLITES]
Sample = namedtuple('Sample', node_fields, defaults=(None,) * len(node_fields))


class TrainingSession(object):
    # We need this coefficient to decode values of coordinates
    COORD_COEFF = 10 ** 4 / 6
    _PACKET_HEADER_LENGTH = 7
    _LAP_DATA_BITS_LENGTH = 416

    def __init__(self, raw_session):
        self.raw = raw_session
        self.info = self._parse_info()
        self.has_hr = self.info['has_hr']
        self.has_gps = self.info['has_gps']

        self.id = None
        # Timezone unaware datetime of the training session's start
        self.start_time = self._format_start_time()
        # UTC datetime of the training session's start
        self.start_utctime = None
        self.name = self.start_time.strftime('%Y-%m-%dT%H:%M:%S')
        # Seconds
        self.duration = self._calculate_duration()
        # Meters
        self.distance = 0
        # Meters per second
        self.max_speed = 0
        self.samples = []

        # Set UTC start time based on local timezone since we
        # don't have any information about user's timezone
        self._set_start_utctime()

        self._cursor = 0
        # We need these variables to manipulate with cursor
        # while parsing values that freeze
        self._zero_delta_counter = {field: 0 for field in list(SampleFields)}
        self._prefixless_zero_sat = False

        self._samples_bits = self._get_samples_bits()

    def tobin(self):
        result = []

        for index, packet in enumerate(self.raw):
            # Keep header of the first packet just for convenience of debugging
            start = 0 if index == 0 else self._PACKET_HEADER_LENGTH
            # Cut off useless trailing zero bytes
            is_last = index == len(self.raw) - 1
            if is_last:
                packet = utils.pop_zeroes(packet[start:])
            else:
                packet = packet[start:-59]

            result.append(''.join([utils.get_bin(byte, 8) for byte in packet]))

        return ''.join(result)

    # TODO: Make it less error-prone.
    # This code is prone to critical errors since changing
    # settings in the watch (e.g. enabling automatic lap) might affect it.
    def parse_samples(self):
        """Parses periodic data recorded with fixed interval."""
        try:
            self.samples = [self._parse_first_sample()]

            while (
                self._cursor < len(self._samples_bits) and len(self._next_bits(7)) > 5
            ):
                hr = self._parse_hr() if self.has_hr else None

                if not self.has_gps:
                    self.samples.append(Sample(hr))
                    continue

                # We won't use these values but instead calculate
                # them using lat and lon
                self._parse_speed()
                self._parse_distance()

                # 24 bits for lon and lat delta
                # Example: 000001101001 (lon) 111111011010 (lat)
                lon, lat = self._parse_coords()

                # TODO: This code has to be tested on more samples
                # to confirm the pattern.
                if self._has_lap_data():
                    sat_after_lap = self._next_bits(9) == '0' * 9
                    if not sat_after_lap:
                        self._parse_satellites()

                    self._cursor += self._LAP_DATA_BITS_LENGTH

                    if sat_after_lap:
                        self._parse_satellites()
                else:
                    self._parse_satellites()

                # Skip undefined 10 bits
                self._cursor += 10

                prev = self._prev_sample()
                distance = self._calculate_distance((prev.lat, prev.lon), (lat, lon))
                self.distance += distance

                # Meteres per second
                speed = distance / self.info['sample_rate']
                if speed > self.max_speed:
                    self.max_speed = speed

                self.samples.append(Sample(hr, lon, lat, distance, speed))
        except Exception as e:
            raise ParserError(e)

    def _next_bits(self, length):
        return self._samples_bits[self._cursor : self._cursor + length]

    def _parse_info(self):
        first_packet = self.raw[0]

        # Dict that maps TrainingSession's attribute to its value in raw session.
        # Formatting function applied if needed.
        field_to_value_map = {
            'user_hr_max': 219,
            'user_hr_rest': 54,
            'user_hr_min': 50,
            'year': (44, lambda x: x + 1920),
            'month': 43,
            'day': 42,
            'hour': (41, bcd_to_int),
            'minute': (40, bcd_to_int),
            'second': (39, bcd_to_int),
            'duration_hours': (38, bcd_to_int),
            'duration_minutes': (37, bcd_to_int),
            'duration_seconds': (36, bcd_to_int),
            'duration_tenth': (35, bcd_to_int),
            'hr_max': 205,
            'hr_min': 203,
            'hr_avg': 201,
            'has_hr': (165, bool),
            'has_gps': (166, bool),
            # 0 (byte value) => 1 (sample rate in seconds)
            # 1 => 2, 2 => 5, 3 => 15, 4 => 60
            'sample_rate': (167, lambda x: (1, 2, 5, 15, 60)[x]),
        }

        info = {}
        for field, value in field_to_value_map.items():
            if isinstance(value, int):
                data = first_packet[value]
            else:
                index, formatter = value
                data = formatter(first_packet[index])

            info[field] = data

        return info

    def _format_start_time(self):
        fields = ('year', 'month', 'day', 'hour', 'minute', 'second')
        datetime_tuple = tuple(v for k, v in self.info.items() if k in fields)

        return datetime.datetime(*datetime_tuple)

    def _set_start_utctime(self, timezone=None):
        self.start_utctime = utils.datetime_to_utc(self.start_time, timezone)
        self.id = self.start_utctime.strftime('%Y-%m-%dT%H:%M:%SZ')

    def _calculate_duration(self):
        return (
            self.info['duration_hours'] * 3600
            + self.info['duration_minutes'] * 60
            + self.info['duration_seconds']
        )

    def _process_hr_bits(self, input_val):
        val_type = HRType(input_val[0:2])

        if self._is_frozen(SampleFields.HR) and val_type != HRType.FULL_WITH_PREFIX:
            return 0, None, 1

        type_offset_map = {
            HRType.FULL_WITH_PREFIX: 3,
            HRType.FULL_PREFIXLESS: 0,
            HRType.POS_DELTA: 2,
            HRType.NEG_DELTA: 2,
        }
        type_offset = type_offset_map[val_type]
        end = 11 if val_type in (HRType.FULL_WITH_PREFIX, HRType.FULL_PREFIXLESS) else 6
        val = input_val[type_offset:end]

        if len(val) < 4:
            val = '{:<04s}'.format(val)

        if val_type == HRType.NEG_DELTA:
            val = utils.twos_complement_to_int(val)
        else:
            val = int(val, 2)

        return val, val_type, end

    def _is_frozen(self, field):
        """
        Field is frozen if there was two zero deltas in a row.
        Frozen fields won't be parsed. Their value is assumed be
        the same until unfrozen.
        """
        return self._zero_delta_counter[field] >= 2

    def _reset_zero_delta_counter(self, field):
        self._zero_delta_counter[field] = 0

    def _handle_delta(self, field, delta):
        """Counts zero deltas if they occur one by one."""
        if delta == 0:
            self._zero_delta_counter[field] += 1
        else:
            self._zero_delta_counter[field] = 0

    def _format_coord_frac(self, val):
        if isinstance(val, str):
            val = int(val, 2)

        return round((val * self.COORD_COEFF) / 10 ** 9, 9)

    def _format_coord(self, coord_int, coord_frac):
        return int(coord_int, 2) + self._format_coord_frac(coord_frac)

    def _format_coord_delta(self, val):
        if val[:1] == '1':
            val = utils.twos_complement_to_unsigned(val, 12)

        return self._format_coord_frac(val)

    def _calculate_distance(self, coord1, coord2):
        return geopy.distance.distance(coord1, coord2).meters

    def _parse_first_coords(self, data):
        """Returns initial coordinates.

        lon_int  lon_frac             lat_int  lat_frac
        00100111 01100111110010011111 00110110 01011010011111011110
        """
        int_part_len = 8

        lat_end = len(data)
        lon_end = int(lat_end / 2)

        lon_int_end = int_part_len
        lat_int_end = lon_end + int_part_len

        lon_int = data[:lon_int_end]
        lon_frac = data[lon_int_end:lon_end]

        lat_int = data[lon_end:lat_int_end]
        lat_frac = data[lat_int_end:lat_end]

        Coords = namedtuple('Coords', ['lon', 'lat'])
        return Coords(
            self._format_coord(lon_int, lon_frac), self._format_coord(lat_int, lat_frac)
        )

    def _prev_sample(self, field=None):
        sample = self.samples[-1]
        if field is None:
            return sample

        return getattr(sample, field.value)

    def _parse_first_sample(self):
        if self.has_gps:
            # The purpose of the first 22 bits is unknown
            self._cursor = 22

        if self.has_hr:
            hr, _, offset = self._process_hr_bits(self._samples_bits[self._cursor :])
            self._cursor += offset

        if not self.has_gps:
            return Sample(hr)

        # Next 16 bits contain speed.
        # All distance, speed and altitude values depend on US/Euro
        # unit selection (km / miles, km/h /mph, m / ft)
        #
        # Example for 3.3 km/h:
        # 10000000 (prefix) 0011 (integer part as is) 0101 (fractional part)
        # Fractional part is calculated with unknown formula.
        # I figured out that if we do int('0101', 2) / k, where k = 10/6,
        # we will get approximate value for fractional part.
        #
        # We won't parse speed data.
        # Just skip those bits plus 29 bits next to them for distance covered.
        self._cursor += 45

        # Next 56 bits contain first longitude and latitude
        coords_end = self._cursor + 56
        coords = self._parse_first_coords(self._samples_bits[self._cursor : coords_end])

        # Set start time based on timezone of coordinates
        timezone = utils.timezone_by_coords(coords.lat, coords.lon)
        self._set_start_utctime(timezone)

        self._cursor = coords_end

        # Next 7 bits contain number of satellites used
        # Example: 001 (prefix) 0100 (value)
        # We won't use it.
        self._cursor += 7
        # The purpose of next 23 bits is unknown
        self._cursor += 23

        return Sample(hr if self.has_hr else None, *coords, distance=0.0, speed=0.0)

    def _parse_hr(self):
        field = SampleFields.HR
        # Maximum 11 bits for hr data
        bits = self._next_bits(11)
        hr, val_type, offset = self._process_hr_bits(bits)

        # HR is going to "freeze" with two zero deltas in a row.
        # 011 value type (full value) unfreezes it:
        #
        # 10 0010       +2
        # 10 0000       +0
        # 10 0000       +0
        # 1             +0 frozen
        # 011 10010100  148

        is_full = val_type in (HRType.FULL_WITH_PREFIX, HRType.FULL_PREFIXLESS)
        if is_full:
            self._reset_zero_delta_counter(field)
        else:
            self._handle_delta(field, hr)

        self._cursor += offset

        return hr if is_full else self._prev_sample(field) + hr

    def _parse_speed(self):
        """Parse 7 (delta) or 16 (full value) bits that contain speed.

        We are going to use int(x, 2) / k formula for
        examples below.

            0000011 +2
            0000110 +4
            1111011 -4 (two's complement)

        Speed is going to "freeze" with two zero deltas in a row.
        Prefix 10000000 with full 7-bit value next to it  unfreezes it:

            0000000 0001011 (second chunk is the distance)
            0000000 0001110
            0001110 (no speed data, just distance's 7 bits)
            10000000 1010 0010 0001111

        Full value might appear even without speed being frozen.
        """

        # We are not going to use speed so we don't care about its value.
        field = SampleFields.SPEED
        offset = 7
        speed = int(self._next_bits(7), 2)

        if self._is_frozen(field):
            offset = 0
            speed = 0

        is_full = self._next_bits(7) == '1000000'
        if is_full:
            offset = 16
            speed = int(self._samples_bits[self._cursor + 7 : self._cursor + 16], 2)
            self._reset_zero_delta_counter(field)
        else:
            self._handle_delta(field, speed)

        self._cursor += offset

        return speed

    def _parse_distance(self):
        """Parses 7 or 29 bits that contain distance covered.

        7 bits contain amount of distance units covered
        over a sample of time since previous interval.

        29 bits contain distance covered since the
        session start.

        Distance is going to "freeze" with two zeroes in a row.
        We assume prefix 10000000 unfreezes it.

            0001111                          15
            0000010                           2
            0000000                           0
            0000000                           0
                                              0
            10000000 000000000010010101011 1195
        """
        field = SampleFields.DISTANCE
        offset = 7
        dist = int(self._next_bits(7), 2)

        if self._is_frozen(field):
            offset = 0
            dist = 0

        is_full = self._next_bits(8) == '10000000'
        if is_full:
            offset = 29
            dist = int(self._samples_bits[self._cursor + 8 : self._cursor + 29], 2)
            self._reset_zero_delta_counter(field)
        else:
            self._handle_delta(field, dist)

        self._cursor += offset

        return dist

    def _parse_coords(self):
        lon = self._parse_coord(SampleFields.LON)
        lat = self._parse_coord(SampleFields.LAT)

        return (lon, lat)

    def _parse_coord(self, coord_name):
        offset = 12
        raw_value = self._next_bits(offset)

        # 12 bits of delta
        prev = self._prev_sample(coord_name)
        value = self._format_coord_delta(raw_value)
        is_full = False

        if self._is_frozen(coord_name):
            offset = 0
            value = 0

            int_end = self._cursor + 8
            frac_end = int_end + 20

            full_value = self._format_coord(
                self._samples_bits[self._cursor : int_end],
                self._samples_bits[int_end:frac_end],
            )

            is_full = int(full_value) == int(prev)
            if is_full:
                offset = 28
                value = full_value
                self._reset_zero_delta_counter(coord_name)

        if not is_full:
            self._handle_delta(coord_name, int(raw_value, 2))

        self._cursor += offset

        return value if is_full else round(prev + value, 9)

    # TODO: Seems like there is a lot of edge cases that may lead to errors.
    # Figure them out and handle. For now it covers most common cases.
    def _parse_satellites(self):
        """
        Parses 4 (delta) or 7 (full value) bits contain number
        of satellites used to calculate the GPX fix.

        There might be no value at all ("frozen" value) if delta
        is 0 and the previous two deltas were also 0:

            0000 0101111110 (purpose of these 10 bits is unknown)
            0000 0110111111
            0101111111 (value is frozen, only undefined 10 bits are left)
            0101111111

        And there is a prefix (001) to exit out of this state:

            0000 0101111111       +0 delta
            0000 0101111111       +0 delta
            0101111111            +0 frozen
            0101111111            +0 frozen
            001 0111 0101111111    7 full value with prefix
            0001 0101111111       +1 delta

        Prefix is a flag that says there is a full value (not delta) 4 bits next to it.

        There is also might be a prefixless full zero value that appears
        due to unknown circumstances.

            0000000 0101101111

        Prefixless full zero value:
        - doesn't trigger freezing process
        - next value might be prefixed full value
            0000000 0101101111
            001 0011 0101101111
        - next value might be delta zero value
            0000000 0101111110
            0000 0101111111

        In frozen state there might be prefixless full value that appears
        due to unknown circumstances.

            0000 0101111111     +0 delta
            0000 0101111111     +0 delta
            0101101111          +0 frozen
            0000101 0101100000   5 full prefixless value
            001 0101 0100111111  5 full value with prefix

        Prefixless full value does't trigger unfreeze process.
        """
        field = SampleFields.SATELLITES
        offset = 4
        sat = self._next_bits(4)
        prefixless_value = int(self._next_bits(7), 2)

        # After a sample with prefixless zero value there
        # migh be full value with prefix.
        if self._prefixless_zero_sat and sat[:3] == '001':
            offset = 7

        if self._is_frozen(field):
            # There might be prefixless full value
            #
            # NOTE: condition below might break since we assume
            # that prefixless full value can't represent more
            # than 31 satellites (we need this assumption to parse
            # bits that follow satellites bits).
            offset = 0 if prefixless_value > 31 else 7
            if sat[:3] == '001':
                self._reset_zero_delta_counter(field)

        # Save self._prefixless_zero_sat for next sample, since
        # there might be full value with prefix even though field
        # is not frozen.
        self._prefixless_zero_sat = prefixless_value == 0
        if self._prefixless_zero_sat:
            offset = 7

        is_delta = offset == 4
        if is_delta:
            self._handle_delta(field, int(sat, 2))
        elif not self._is_frozen(field):
            self._reset_zero_delta_counter(field)

        self._cursor += offset

        return sat

    # TODO: Make more reliable algorithm for lap data detection.
    def _has_lap_data(self):
        prev = self._prev_sample()
        lon = utils.get_bin(int(prev.lon), 8)
        lat = utils.get_bin(int(prev.lat), 8)

        # Since the pattern is unknown and we don't have better ideas
        # it's going to be another assumption.
        # If there is lap data, it always contains longitude and latitude.
        # But the amount of bits before is inconsistent. We assume
        # there is from 250 to 290 bits.
        pat = f'.{{250,290}}{lon}.{{24}}{lat}'
        return re.match(pat, self._next_bits(self._LAP_DATA_BITS_LENGTH)) is not None

    def _get_samples_bits(self):
        """Returns bits with session's samples.

        Session's samples start at the 349th byte (if session has gps data)
        or at 351th (without gps data).
        """
        start = 349 if self.has_gps else 351
        return self.tobin()[start * 8 :]
