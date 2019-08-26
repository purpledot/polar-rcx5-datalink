import os
import sys
import pickle

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from polar_rcx5_datalink.parser import TrainingSession


def raw_sessions_with_expected_samples():
    filename = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__), 'raw_sessions_with_expected_samples.pickle'
        )
    )
    with open(filename, 'rb') as f:
        while True:
            try:
                yield pickle.load(f)
            except EOFError:
                break


@pytest.mark.parametrize(
    'raw_session,expected_samples', raw_sessions_with_expected_samples()
)
def test_parse_samples(raw_session, expected_samples):
    ts = TrainingSession(raw_session)
    ts.parse_samples()
    assert ts.samples == expected_samples
