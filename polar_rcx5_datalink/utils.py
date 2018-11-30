import os
from contextlib import contextmanager

import click
import pytz
import tzlocal
from timezonefinder import TimezoneFinder


def print_error(message):
    click.secho(message, bg='red')


@contextmanager
def ignored(*exceptions):
    try:
        yield
    except exceptions:
        pass


def file_dir(file):
    return os.path.abspath(os.path.dirname(file))


def get_bin(val, length=16):
    """16-bit binary reptesentation of val"""
    return format(val, 'b').zfill(length)


def bcd_to_int(input_val):
    """Converts Binary Coded Decimal to integer"""
    if isinstance(input_val, int):
        input_val = get_bin(input_val, 8)

    n = 4
    digits = [int(input_val[i : i + n], 2) for i in range(0, len(input_val), n)]

    return int(''.join([str(d) for d in digits]))


def get_bin_slice(val, start=0, end=None):
    byte_string = get_bin(val)

    if end is None:
        end = len(byte_string)

    return int(byte_string[start:end], 2)


def pop_zeroes(items):
    """Removes trailing zeros from a list"""
    index = next(i for i, v in enumerate(reversed(items)) if v != 0)
    return items[:-index]


def most_significant_byte(val):
    return get_bin_slice(val, end=8)


def least_significant_byte(val):
    return get_bin_slice(val, start=-8)


def starts_with(a, b):
    return a[: len(b)] == bytearray(b)


def int_to_twos_complement(val, length=8):
    """Convers integer into two's complement binary representation"""
    if val >= 0:
        return get_bin(val, length)

    invertor = int('1' * length, 2)
    return format((abs(val) ^ invertor) + 1, 'b')


def twos_complement_to_int(val, length=4):
    """
    Two's complement representation to integer.

    We assume that the number is always negative.

    1. Invert all the bits through the number
    2. Add one
    """
    invertor = int('1' * length, 2)

    return -((int(val, 2) ^ invertor) + 1)


def twos_complement_to_unsigned(*args, **kwargs):
    """Converts two's complement into unsigned binary integer representation"""
    return bin(twos_complement_to_int(*args, **kwargs))


def timezone_by_coords(lat, lng):
    tf = TimezoneFinder()
    timezone = tf.timezone_at(lat=lat, lng=lng)
    if timezone is None:
        timezone = str(tzlocal.get_localzone())

    return timezone


def datetime_to_utc(dt, timezone=None):
    if timezone is None:
        timezone = tzlocal.get_localzone()
    else:
        timezone = pytz.timezone(timezone)

    local_dt = timezone.localize(dt, is_dst=None)

    return local_dt.astimezone(pytz.utc)
