import json
import os
import pathlib
import sys
from functools import wraps

import click
import loguru

import polar_rcx5_datalink.strava_sync.app as strava_sync
from .__version__ import __version__
from .converter import FORMAT_CONVERTER_MAP
from .datalink import DataLink
from .exceptions import ParserError, SyncError
from .parser import TrainingSession
from .utils import report_error, report_warning, to_stdout

ENVVAR_PREFIX = 'RCX5'
DEFAULT_STRAVASYNC_HOST = '127.0.0.1'
DEFAULT_STRAVASYNC_PORT = 8000
DEFAULT_EXPORT_FORMAT = 'tcx'
LOGS_PATH = os.path.join(
    str(pathlib.Path.home()), 'Documents/rcx5' if os.name == 'nt' else '.rcx5'
)

log_config = {
    'handlers': [
        # {'sink': sys.stdout},
        {
            'sink': os.path.join(LOGS_PATH, 'error.log'),
            'rotation': '100 MB',
            'retention': '10 days',
        }
    ]
}
loguru.logger.configure(**log_config)


def get_raw_sessions(from_dir=None):
    """Returns unprocessed training sessions.

    Each session is a list of packets and each packet
    is a list of bytes received from the watch.
    """
    if from_dir is not None:
        raw_sessions = raw_sessions_from_dir(from_dir)
    else:
        try:
            raw_sessions = raw_sessions_from_watch()
        except SyncError as err:
            report_error(str(err))
            sys.exit(1)

    return raw_sessions


def raw_sessions_from_dir(path):
    for filename in sorted(os.listdir(path)):
        with open(os.path.join(path, filename)) as f:
            yield json.load(f)


def raw_sessions_from_watch():
    with DataLink() as dl:
        dl.synchronize()
        return dl.sessions


def parse_raw_sessions(raw_sessions, from_date=None, to_date=None):
    for rs in raw_sessions:
        sess = TrainingSession(rs)
        if from_date is not None and sess.start_time < from_date:
            continue
        if to_date is not None and sess.start_time > to_date:
            continue

        yield sess


def load_sessions(func):
    """Loads parsed sessions as a first argument of a function"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        raw_sessions = get_raw_sessions(kwargs.pop('sessions_dir', None))
        sessions = parse_raw_sessions(
            raw_sessions, kwargs.pop('from_date', None), kwargs.pop('to_date', None)
        )

        return func(sessions, *args, **kwargs)

    return wrapper


@click.group()
@click.version_option(version=__version__)
def cli():
    """Polar RCX5 training session exporter.

    Export Polar RCX5 training sessions in raw or tcx format.
    You also can upload them to Strava with a single command.

    \b
    Examples:
      rcx5 export --out /path/for/exported/files/
      rcx5 stravasync --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET
    """
    pass


def common_options(func):
    @wraps(func)
    @click.option(
        '-s',
        '--sessions-dir',
        type=click.Path(exists=True),
        help='Directory of raw training sessions.',
    )
    @click.option(
        '--from-date',
        type=click.DateTime(),
        help='Filter sessions that have started at this date or after.',
    )
    @click.option(
        '--to-date',
        type=click.DateTime(),
        help='Filter sessions that have started at this date or before.',
    )
    def newfunc(*args, **kwargs):
        return func(*args, **kwargs)

    return newfunc


@cli.command()
@click.option(
    '-o',
    '--out',
    type=click.Path(exists=True, writable=True),
    default=os.getcwd(),
    help='Where to save the output. Current working directory by default.',
)
@click.option(
    '-f',
    '--format',
    'file_format',
    type=click.Choice(['raw', 'bin', 'tcx']),
    default=DEFAULT_EXPORT_FORMAT,
    help='Export file format.',
    show_default=True,
)
@common_options
@load_sessions
def export(sessions, out, file_format):
    """Exports training sessions."""
    to_stdout('[export] Exporting training sessions')
    for sess in sessions:
        if file_format == 'tcx' and not sess.has_gps:
            report_warning(f'{sess.name} has no GPS data')
            continue

        try:
            converter = FORMAT_CONVERTER_MAP[file_format](sess)
        except ParserError:
            err_msg = f"Can't parse samples of session #{sess.id}"
            loguru.logger.exception(err_msg)
            report_warning(err_msg)
            continue

        converter.write(out)


@cli.command(name='stravasync')
@click.option('-h', '--host', default=DEFAULT_STRAVASYNC_HOST)
@click.option('-p', '--port', type=int, default=DEFAULT_STRAVASYNC_PORT)
@click.option(
    '--client-id',
    type=int,
    required=True,
    help='Application’s ID, obtained during registration',
)
@click.option(
    '--client-secret',
    required=True,
    help='Application’s secret, obtained during registration.',
)
@common_options
@load_sessions
def stravasync(sessions, host, port, client_id, client_secret):
    """Helps to synchronize training sessions with Strava.

    Before getting started you need to register an application
    https://strava.com/settings/api (Authorization Callback Domain MUST be 0.0.0.0).

    A registered application will be assigned a Client id and Client secret.
    Provide those in options --client-id and --client-secret respectively.

    \b
    Examples:
      rcx5 stravasync --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET
      \b
      # You can use environment variables to pass --client-id and --client-secret.
      \b
      export RCX5_STRAVASYNC_CLIENT_ID=YOUR_CLIENT_ID
      export RCX5_STRAVASYNC_CLIENT_SECRET=YOUR_CLIENT_SECRET
      rcx5 stravasync
    """
    strava_sync.run_app(
        host, port, client_id, client_secret, [s for s in sessions if s.has_gps]
    )


def main():
    cli(auto_envvar_prefix=ENVVAR_PREFIX)
