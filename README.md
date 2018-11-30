# polar-rcx5-datalink
Command-line program to export Polar RCX5 training sessions in raw or tcx format. You also can upload them to Strava with a single command.

# Table of contents
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Examples](#examples)
- [Description](#description)

# Requirements
- Python >=3.7
- [libusb](https://libusb.info/) >=1.0, <=1.0.21 (PyUSB has [issues](https://github.com/libusb/libusb/issues/412) with libusb-1.0.22 backend.)


If you are using Linux, chances are your distribution already includes libusb.

How to install libusb on Windows: https://github.com/pyusb/pyusb/issues/120#issuecomment-322058585

# Installation
    pip install polar-rcx5-datalink

# Usage
1. Plug in [Polar DataLink](https://support.polar.com/en/support/tips/Polar_DataLink)
2. Select "Connect > Start" from your watch
3. Run a [command](#description)

# Examples
### Export training sessions in current directory

    rcx5 export

### Export training sessions to /where/to/export/files/

    rcx5 export --out /where/to/export/files/ --format tcx

### Filter by date

    rcx5 export --from-date 2018-11-20 --to-date 2018-11-25

### Sync training sessions with Strava

    rcx5 stravasync --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET

# Description
    Usage: rcx5 [OPTIONS] COMMAND [ARGS]...

    Options:
      --version  Show the version and exit.
      --help     Show this message and exit.

    Commands:
      export      Exports training sessions.
      stravasync  Helps to synchronize training sessions with Strava.

## rcx5 export
    Usage: rcx5 export [OPTIONS]

      Exports training sessions.

    Options:
      -o, --out PATH                  Where to save the output. Current working 
                                      directory by default.
      -f, --format [raw|bin|tcx]      Export file format.
      -s, --sessions-dir PATH         Directory of raw training sessions.
      --from-date [%Y-%m-%d|%Y-%m-%dT%H:%M:%S|%Y-%m-%d %H:%M:%S]
                                      Filter sessions that have started at this
                                      date or after.
      --to-date [%Y-%m-%d|%Y-%m-%dT%H:%M:%S|%Y-%m-%d %H:%M:%S]
                                      Filter sessions that have started at this
                                      date or before.
      --help                          Show this message and exit.

## rcx5 stravasync
    Usage: rcx5 stravasync [OPTIONS]

      Helps to synchronize training sessions with Strava.

      Before getting started you need to register an application
      https://strava.com/settings/api (Authorization Callback Domain MUST be
      0.0.0.0).

      A registered application will be assigned a Client id and Client secret.
      Provide those in options --client-id and --client-secret respectively.

      Examples:
        rcx5 strava-syncs --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET

        # You can use environment variables to pass --client-id and --client-secret.

        export RCX5_STRAVASYNC_CLIENT_ID=YOUR_CLIENT_ID
        export RCX5_STRAVASYNC_CLIENT_SECRET=YOUR_CLIENT_SECRET
        rcx5 stravasync

    Options:
      -p, --port INTEGER
      --client-id INTEGER             Strava application’s ID, obtained during
                                      registration  [required]
      --client-secret TEXT            Strava application’s secret, obtained during
                                      registration.  [required]
      -s, --sessions-dir PATH         Directory of raw training sessions.
      --from-date [%Y-%m-%d|%Y-%m-%dT%H:%M:%S|%Y-%m-%d %H:%M:%S]
                                      Filter sessions that have started at this
                                      date or after.
      --to-date [%Y-%m-%d|%Y-%m-%dT%H:%M:%S|%Y-%m-%d %H:%M:%S]
                                      Filter sessions that have started at this
                                      date or before.
      --help                          Show this message and exit.