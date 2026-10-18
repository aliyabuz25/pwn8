import struct
import unittest
from pathlib import Path
from unittest.mock import Mock
from remed1st.boot_display import encode_frame, screen_svg, patch_startup
from remed1st.pipeline import IOS511Pipeline


class BootDisplayTests(unittest.TestCase):
    def test_initial_display_starts_from_actual_ramdisk_entrypoint(self):
        patched=patch_startup(b'#!/bin/sh\nmount /\n/sbin/sshd\nother-command\n')
        self.assertIn(b'display.log 2>&1 &\n/sbin/sshd\n',patched)
        self.assertIn(b'exec >/remed1st-screen/boot.log 2>&1',patched)
        self.assertIn(b'other-command',patched)
        with self.assertRaises(RuntimeError):patch_startup(b'unknown script')

    def test_frame_header_and_length_match_device_contract(self):
        data=encode_frame(bytes(640*960))
        self.assertEqual(struct.unpack('<4sIII',data[:16]),(b'RMD1',640,960,1))
        self.assertEqual(len(data),640*960+16)
        with self.assertRaises(ValueError):encode_frame(b'bad')

    def test_screen_uses_white_vector_without_app_icon_background(self):
        svg=screen_svg('<svg><rect fill="gray"/><path d="M0 0h2v2z" fill="red"/></svg>', 'Installing Cydia')
        self.assertIn('fill="#ffffff"',svg)
        self.assertNotIn('fill="gray"',svg)
        self.assertIn('Installing Cydia',svg)

    def test_unknown_stage_never_sends_files(self):
        pipeline=IOS511Pipeline();pipeline.copy=Mock()
        with self.assertRaises(ValueError):pipeline.phone_status(Mock(),'made-up')
        pipeline.copy.assert_not_called()

    def test_progress_upload_and_display_must_be_acknowledged(self):
        pipeline=IOS511Pipeline();pipeline.assets=Path('/assets')
        pipeline.copy=Mock();pipeline.ssh=Mock(return_value=(0,b'remed1st screen updated\n'))
        self.assertTrue(pipeline.phone_status(Mock(),'cydia'))
        self.assertEqual(pipeline.copy.call_args.args[1],Path('/assets/screen-cydia.rmd'))
        pipeline.ssh.return_value=(1,b'Unsupported framebuffer')
        self.assertFalse(pipeline.phone_status(Mock(),'cydia'))
