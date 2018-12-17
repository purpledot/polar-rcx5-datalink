import os
import datetime
import json
import xml.etree.ElementTree as ET

from .exceptions import ConverterError


class Converter(object):
    _SUFFIX = ''

    def __init__(self, training_session):
        self.training_session = training_session
        base_filename = self.training_session.start_time.strftime('%Y%m%dT%H%M%S')
        self.filename = base_filename + self._SUFFIX

    def _get_filepath(self, out):
        return os.path.join(out, self.filename)


class BinaryConverter(Converter):
    def write(self, out):
        with open(self._get_filepath(out), 'w') as f:
            packet_as_bin = self.training_session.tobin()
            f.write(f'{packet_as_bin}')


class RawConverter(Converter):
    _SUFFIX = '.json'

    def write(self, out):
        with open(self._get_filepath(out), 'w') as f:
            return f.write(json.dumps(self.training_session.raw))


class TCXConverter(Converter):
    _SUFFIX = '.tcx'
    _ISO8601_FORMAT = '%Y-%m-%dT%H:%M:%SZ'

    def __init__(self, training_session, sport='Other'):
        Converter.__init__(self, training_session)
        self.sport = sport
        self.training_session.parse_samples()
        self._convert()

    def _tcx_container(self):
        sess = self.training_session

        root = ET.Element(
            'TrainingCenterDatabase',
            attrib={
                'xsi:schemaLocation': (
                    'http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2 '
                    'http://www.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd'
                ),
                'xmlns:ns5': 'http://www.garmin.com/xmlschemas/ActivityGoals/v1',
                'xmlns:ns3': 'http://www.garmin.com/xmlschemas/ActivityExtension/v2',
                'xmlns:ns2': 'http://www.garmin.com/xmlschemas/UserProfile/v2',
                'xmlns': 'http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2',
                'xmlns:xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            },
        )

        activities = ET.SubElement(root, 'Activities')
        activity = ET.SubElement(activities, 'Activity', attrib={'Sport': self.sport})

        start_time = sess.start_utctime.strftime(self._ISO8601_FORMAT)
        ET.SubElement(activity, 'Id').text = start_time
        lap = ET.SubElement(activity, 'Lap', attrib={'StartTime': start_time})

        stats = (
            ('TotalTimeSeconds', sess.duration),
            ('DistanceMeters', '{0:.2f}'.format(sess.distance)),
            ('MaximumSpeed', '{0:.1f}'.format(sess.max_speed)),
        )
        for tag, value in stats:
            ET.SubElement(lap, tag).text = str(value)

        hr_data = (
            ('AverageHeartRateBpm', sess.info['hr_avg']),
            ('MaximumHeartRateBpm', sess.info['hr_max']),
        )
        for tag, val in hr_data:
            container = ET.SubElement(lap, tag)
            ET.SubElement(container, 'Value').text = str(val)

        ET.SubElement(lap, 'Intensity').text = 'Active'
        ET.SubElement(lap, 'TriggerMethod').text = 'Manual'

        track = ET.SubElement(lap, 'Track')

        return root, track

    def _tcx_trackpoints(self):
        sess = self.training_session

        trackpoints = []
        distance = 0.0
        for sample_index, sample in enumerate(sess.samples):
            trackpoint = ET.Element('Trackpoint')

            time = sess.start_utctime + datetime.timedelta(
                seconds=sess.info['sample_rate'] * sample_index
            )
            ET.SubElement(trackpoint, 'Time').text = time.strftime(self._ISO8601_FORMAT)

            position = ET.SubElement(trackpoint, 'Position')
            coords = (('LatitudeDegrees', sample.lat), ('LongitudeDegrees', sample.lon))
            for tag, val in coords:
                ET.SubElement(position, tag).text = '{0:.7f}'.format(val)

            distance += sample.distance
            ET.SubElement(trackpoint, 'DistanceMeters').text = '{0:.1f}'.format(
                distance
            )

            if sess.has_hr:
                hr = ET.SubElement(trackpoint, 'HeartRateBpm')
                ET.SubElement(hr, 'Value').text = str(sample.hr)

            extensions = ET.SubElement(trackpoint, 'Extensions')
            tpx = ET.SubElement(extensions, 'TPX')
            ET.SubElement(tpx, 'Speed').text = '{0:.1f}'.format(sample.speed)

            trackpoints.append(trackpoint)

        return trackpoints

    def _convert(self):
        if not self.training_session.has_gps:
            raise ConverterError(
                "Can't convert to TCX: training session doesn't have gps data"
            )

        root, track = self._tcx_container()
        track.extend(self._tcx_trackpoints())

        self.element_tree = ET.ElementTree(root)

    def tostring(self):
        return ET.tostring(self.element_tree.getroot(), encoding='utf8')

    def write(self, out):
        return self.element_tree.write(
            self._get_filepath(out), encoding='utf-8', xml_declaration=True
        )


FORMAT_CONVERTER_MAP = {
    'bin': BinaryConverter,
    'tcx': TCXConverter,
    'raw': RawConverter,
}
