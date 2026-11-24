import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import zine
from zinemaker.server import Desk


class LaunchTests(unittest.TestCase):
    def test_gui_without_arguments_opens_before_creating_a_project(self):
        with (
            patch.object(sys, "argv", ["zine.py"]),
            patch.object(zine, "serve") as serve,
            patch.object(zine, "Project") as project,
        ):
            zine.main()
        project.assert_not_called()
        serve.assert_called_once_with(None, 0, True)
        self.assertIsNone(Desk(None).state()["id"])

    def test_explicit_folder_still_opens_the_issue(self):
        with tempfile.TemporaryDirectory() as folder:
            with (
                patch.object(sys, "argv", ["zine.py", folder]),
                patch.object(zine, "serve") as serve,
            ):
                zine.main()
            issue = serve.call_args.args[0]
            self.assertEqual(issue.source, Path(folder).resolve())
            self.assertTrue(issue.manifest.is_file())

    def test_headless_export_still_defaults_to_cwd(self):
        with (
            patch.object(sys, "argv", ["zine.py", "--export"]),
            patch.object(zine, "Project") as project,
            patch.object(zine, "publish") as publish,
            patch("builtins.print"),
        ):
            zine.main()
        project.assert_called_once_with(Path.cwd(), None)
        publish.assert_called_once_with(project.return_value, project.return_value.data)
