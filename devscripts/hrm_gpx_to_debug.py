"""
Command-line program that parses hrm and gpx files and converts them
into a file that helps with reverse engineering of the RCX5 protocol.

python hrm_gpx_to_debug.py --dir /path/to/hrm-and-gpx-files/ --out /path/to/output-dir/
"""

import os
import sys
import itertools
from collections import namedtuple

import click
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polar_rcx5_datalink.utils import get_bin, int_to_twos_complement
from polar_rcx5_datalink.parser import TrainingSession


def parse_hr(raw_samples):
    data = tuple(int(x.split('\t')[0]) for x in raw_samples if x)
    samples = []
    for i, v in enumerate(data):
        if i > 0:
            v = v - data[i - 1]

        prefix = '10'
        length = 4
        if abs(v) > 15:
            prefix = '011'
            length = 8
        elif v < 0:
            prefix = '11'

        samples.append(f'{prefix}{int_to_twos_complement(v, length)}')

    return samples


def coord_to_bin(coord, length):
    val = round(coord / TrainingSession.COORD_COEFF)
    return int_to_twos_complement(val, length)


def extract_coords(raw_samples):
    Coords = namedtuple('Coords', ['lon', 'lat'])
    Coord = namedtuple('Coord', ['int8', 'frac', 'frac20'])

    samples = []
    for raw_sample in raw_samples:
        (lon_int, lon_frac), (lat_int, lat_frac) = (
            (int(x) for x in coord.split('.'))
            for coord in (raw_sample['lon'], raw_sample['lat'])
        )

        samples.append(
            Coords(
                Coord(get_bin(lon_int, 8), lon_frac, coord_to_bin(lon_frac, 20)),
                Coord(get_bin(lat_int, 8), lat_frac, coord_to_bin(lat_frac, 20)),
            )
        )

    return samples


def format_coords(raw_samples):
    """Formats coords.

    Helps to identify coordinates in binary representation
    of a training session.
    """
    samples = extract_coords(raw_samples)
    for i, coords in enumerate(samples):
        lon, lat = coords

        if i == 0:
            lonlat = f'{lon.int8} {lon.frac20} / {lat.int8} {lat.frac20}'
        else:
            prev_lon, prev_lat = samples[i - 1]
            lon_delta, lat_delta = (lon.frac - prev_lon.frac, lat.frac - prev_lat.frac)
            lonlat = f'{coord_to_bin(lon_delta, 12)}' f'{coord_to_bin(lat_delta, 12)}'

        yield lonlat


def parse(out, files):
    """Makes a debug text file out of gpx and hrm files"""
    hrm_file = None
    gpx_file = None
    for filepath in files:
        if filepath.endswith('.hrm'):
            hrm_file = filepath
        else:
            gpx_file = filepath

    if hrm_file is not None:
        with open(hrm_file) as hrm_file:
            raw_hr_samples = hrm_file.read().split('[HRData]\n')[1].split('\n')
            hr_samples = parse_hr(raw_hr_samples)
    if gpx_file is not None:
        with open(gpx_file) as f:
            gpx_soup = BeautifulSoup(f, 'xml').find_all('trkpt')
            coords = format_coords(gpx_soup)

    hrm_only = hrm_file is not None and gpx_file is None
    if hrm_only:
        with open(out, 'w') as f:
            for i, hr_as_bin in enumerate(hr_samples):
                f.write(f'hr speed: {raw_hr_samples[i]}\n' f'{hr_as_bin}\n\n')
        return

    with open(out, 'w') as f:
        for i, coords_as_bin in enumerate(coords):
            hr_as_bin = ''
            hr_and_speed = ''
            if hrm_file is not None:
                hr_as_bin = hr_samples[i]
                hr_and_speed = raw_hr_samples[i]

            f.write(
                f'lon: {gpx_soup[i]["lon"]}\n'
                f'lat: {gpx_soup[i]["lat"]}\n'
                f'time: {gpx_soup[i].find_next("time").text}\n'
                f'sat: {gpx_soup[i].find_next("sat").text}\n'
                f'hr speed: {hr_and_speed}\n\n'
            )
            f.write(f'{coords_as_bin}\t{hr_as_bin}\n\n')

            if i == 0:
                f.write(f'\n\n\n')


@click.command()
@click.option(
    '--dir',
    'files_dir',
    type=click.Path(exists=True),
    required=True,
    help='Directory of hrm and gps files.',
)
@click.option(
    '-o',
    '--out',
    type=click.Path(exists=True),
    required=True,
    help='Where to save the output',
)
def hrm_gpx_to_debug(files_dir, out):
    for base_filename, filenames in itertools.groupby(
        sorted(os.listdir(files_dir)), key=lambda x: x.split('.')[0]
    ):
        # Split string 18081601 to ['18', '08', '16', '01']
        n = 2
        year, month, day, number = [
            base_filename[i : i + n] for i in range(0, len(base_filename), n)
        ]

        files = (os.path.join(files_dir, name) for name in filenames)
        filename = f'20{year}{month}{day}N{number}'
        parse(os.path.join(out, filename), files)


if __name__ == '__main__':
    hrm_gpx_to_debug()
