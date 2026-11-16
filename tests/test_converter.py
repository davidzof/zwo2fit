"""Regression tests for ZWO to iGPSPORT conversion. Run: python -m unittest discover -s tests -v"""
import struct
import tempfile
import unittest
from pathlib import Path

from zwo_to_igpsport_fit import parse_zwo, make_fit, crc

FIXTURES = Path(__file__).parent / 'fixtures'


def parse_xml(xml, ftp=200, ramp_step=30):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'workout.zwo'
        path.write_text(xml, encoding='utf-8')
        return parse_zwo(path, ftp, ramp_step)


class ZwoWorkoutTests(unittest.TestCase):
    def test_simple_erg_workout(self):
        name, steps = parse_zwo(FIXTURES / 'simple_erg.zwo', 200, 30)
        self.assertEqual(name, 'Simple ERG Workout')
        self.assertEqual(len(steps), 29)
        self.assertEqual(sum(step[1] for step in steps), 32 * 60 * 1000)
        self.assertEqual(steps[10][2], 160)  # 80% of FTP=200
        self.assertEqual([s[2] for s in steps[11:19]], [220, 100] * 4)
        self.assertLess(steps[0][2], steps[9][2])  # Warmup rises
        self.assertGreater(steps[-10][2], steps[-1][2])  # Cooldown falls

    def test_ftp_scaling(self):
        _, a = parse_zwo(FIXTURES / 'freeride.zwo', 200, 30)
        _, b = parse_zwo(FIXTURES / 'freeride.zwo', 240, 30)
        self.assertEqual([a[0][2], b[0][2]], [150, 180])
        self.assertEqual([a[2][2], b[2][2]], [150, 180])

    def test_freeride_open_step(self):
        _, steps = parse_zwo(FIXTURES / 'freeride.zwo', 200, 30)
        self.assertEqual(len(steps), 3)
        self.assertEqual([s[2] for s in steps], [150, None, 150])
        self.assertEqual([s[1] for s in steps], [60000] * 3)

    def test_lactate_workout(self):
        name, steps = parse_zwo(FIXTURES / 'lactate_low_1.zwo', 200, 30)
        self.assertEqual(name, 'Lactate Low 1')
        self.assertEqual(len(steps), 67)
        self.assertEqual(sum(s[1] for s in steps), 3270 * 1000)
        self.assertEqual(steps[-1][2], None)
        self.assertEqual(steps[-1][1], 300000)
        self.assertGreater(steps[-21][2], steps[-2][2])  # Descending Ramp

    def test_partial_ramp_duration(self):
        _, steps = parse_xml('<workout_file><workout><Ramp Duration="75" PowerLow="0.5" PowerHigh="1"/></workout></workout_file>')
        self.assertEqual([s[1] for s in steps], [30000, 30000, 15000])
        self.assertEqual(sum(s[1] for s in steps), 75000)
        self.assertEqual([s[2] for s in steps], sorted(s[2] for s in steps))

    def test_reverse_ramp(self):
        _, steps = parse_xml('<workout_file><workout><Ramp Duration="90" PowerLow="1" PowerHigh="0.5"/></workout></workout_file>')
        self.assertGreater(steps[0][2], steps[-1][2])

    def test_alt_step_names(self):
        _, steps = parse_xml('<workout_file><workout><SolidState Duration="60" Power="0.8"/><Freeride Duration="60"/><MaxEffort Duration="20"/></workout></workout_file>')
        self.assertEqual([s[2] for s in steps], [160, None, None])

    def test_annotations_do_not_add_steps(self):
        _, steps = parse_xml('<workout_file><workout><SteadyState Duration="60" Power="0.8"><textevent timeoffset="20" message="Hi"/></SteadyState><textevent timeoffset="0" message="Hello"/></workout></workout_file>')
        self.assertEqual(len(steps), 1)

    def test_unknown_steps_fail_explicitly(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported ZWO step: Mystery'):
            parse_xml('<workout_file><workout><Mystery Duration="60"/></workout></workout_file>')

    def test_noncycling_workout_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Only bike workouts'):
            parse_xml('<workout_file><sportType>run</sportType><workout><SteadyState Duration="60" Power="0.8"/></workout></workout_file>')

    def test_invalid_duration_rejected(self):
        with self.assertRaisesRegex(ValueError, 'positive duration'):
            parse_xml('<workout_file><workout><SteadyState Duration="0" Power="0.8"/></workout></workout_file>')

    def test_unreasonable_power_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Power outside supported range'):
            parse_xml('<workout_file><workout><SteadyState Duration="60" Power="10"/></workout></workout_file>')


class FitFileTests(unittest.TestCase):
    def test_header_data_size_and_crcs(self):
        _, steps = parse_zwo(FIXTURES / 'freeride.zwo', 200, 30)
        output = make_fit('Test', steps)
        self.assertEqual(output[:1], b'\x0e')
        self.assertEqual(output[8:12], b'.FIT')
        self.assertEqual(struct.unpack_from('<I', output, 4)[0], len(output) - 16)
        self.assertEqual(struct.unpack_from('<H', output, 12)[0], crc(output[:12]))
        self.assertEqual(struct.unpack_from('<H', output, len(output) - 2)[0], crc(output[:-2]))

    def test_fit_open_step_encoding(self):
        _, steps = parse_zwo(FIXTURES / 'freeride.zwo', 200, 30)
        output = make_fit('Test', steps)
        # Step values appear as low/high targets: 1150 for 150W, and 0xffffffff for open.
        self.assertGreaterEqual(output.count(struct.pack('<I', 1150)), 4)
        # Four consecutive invalid uint32 values mark an untargeted step's target fields.
        self.assertIn(b'\xff' * 16, output)

    def test_fit_size_is_stable(self):
        _, steps = parse_zwo(FIXTURES / 'simple_erg.zwo', 200, 30)
        a = make_fit('Test', steps)
        b = make_fit('Test', steps)
        self.assertEqual(len(a), len(b))  # Timestamp may differ between runs


if __name__ == '__main__':
    unittest.main()
