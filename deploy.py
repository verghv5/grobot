#!/usr/bin/python3


import argparse
import os
import shutil
import subprocess
import sys
import time
import unittest

from backend import server
from backend.module_sim import simulator
from backend.module_sim import base_module


""" Script to manage building and testing the web application. """


def build_polymer_app():
  # Get directory that the script it in.
  script_path = os.path.dirname(os.path.realpath(__file__))

  if subprocess.call(["polymer", "build"], cwd=script_path):
    print("ERROR: Polymer build failed!")
    sys.exit(1)

  # TODO (danielp): Figure out why polymer doesn't want to run sw-precache.
  config_path = os.path.join(script_path, "sw-precache-config.js")
  if subprocess.call(["sw-precache", "--config", config_path], cwd=script_path):
    print("ERROR: Generating service worker failed!")
    sys.exit(1)
  # Move the generated file to the right place.
  service_worker_file = os.path.join(script_path, "service-worker.js")
  built_service_worker = os.path.join(script_path,
                                      "build/bundled/service-worker.js")
  os.rename(service_worker_file, built_service_worker)

def run_python_tests():
  """ Runs the Python tests.
  Returns:
    True if the tests all succeed, False if there are failures. """
  print("Starting Python tests...")

  loader = unittest.TestLoader()
  # Get the directory this module is in.
  dir_path = os.path.dirname(os.path.realpath(__file__))
  suite = loader.discover("backend/tests", top_level_dir=dir_path)

  test_result = unittest.TextTestRunner(verbosity=2).run(suite)
  if not test_result.wasSuccessful():
    return False

  return True

def run_js_tests(keep_open=False):
  """ Runs the JavaScript tests.
  Args:
    keep_open: Whether to keep browsers open after running tests.
  Returns:
    True if the tests all succeed, False if there are failures. """
  print("Starting JS tests...")

  # Get the directory this module is in.
  dir_path = os.path.dirname(os.path.realpath(__file__))

  # Run polymer tests directly.
  test_command = ["polymer", "test"]
  if keep_open:
    test_command.append("-p")
  retcode = subprocess.call(test_command, cwd=dir_path)

  if retcode:
    return False
  return True

def run_all_tests(keep_open=False):
  """ Runs all the tests.
  Args:
    keep_open: Whether to keep browsers open after running JS tests.
  Returns:
    True if the tests all succeed, False if there are failures. """
  if not run_python_tests():
    return False
  if not run_js_tests(keep_open=keep_open):
    return False
  return True

def setup_container():
  """ Run setup for containerized deployment.
  Returns:
    Handle to xvfb process. """
  print("Starting xvfb...")

  # The DISPLAY variable should be set in the container.
  display = os.environ["DISPLAY"]

  # Initialize xvfb.
  xvfb = subprocess.Popen(["Xvfb", display, "-ac", "-screen", "0",
                           "1920x1080x24"])

  # Give it a second to start.
  time.sleep(0.5)
  if xvfb.poll():
    # It terminated prematurely.
    print("ERROR: Xvfb terminated unexpectedly!")
    sys.exit(1)

  # Link to our installed bower dependencies. (We'll restore the actual one
  # later.)
  if os.path.exists("bower_components"):
    shutil.move("bower_components", "bower_components-user")
  os.symlink("/bower_components", "bower_components")

  return xvfb

def teardown_container(xvfb):
  """ Tears down the container after testing.
  Args:
    xvfb: The Xvfb process that we started for testing. """
  # We're done with this now.
  xvfb.terminate()

  # Move the user bower components back.
  os.remove("bower_components")
  if os.path.exists("bower_components-user"):
    shutil.move("bower_components-user", "bower_components")

def main():
  parser = argparse.ArgumentParser( \
      description="Run and test the web application.")
  parser.add_argument("-p", "--production", action="store_true",
                      help="Rebuild polymer app and serve from build/bundled.")
  parser.add_argument("-t", "--test-only", action="store_true",
                      help="Only run the tests and nothing else.")
  parser.add_argument("-m", "--module_simulation", action="store_true",
                      help="Run with simulated module stack.")
  parser.add_argument("-f", "--force", action="store_true",
                      help="Continue even if the tests fail.")
  parser.add_argument("-c", "--containerized", action="store_true",
                      help="Use this when running in a container.")
  parser.add_argument("-k", "--keep_open", action="store_true",
                      help="Keep browsers open after running tests.")
  args = parser.parse_args()

  # Build the polymer app.
  if args.production:
    print("Building polymer app...")
    build_polymer_app()

  # Initialize stuff for the container.
  xvfb = None
  if args.containerized:
    xvfb = setup_container()

  # Run the tests.
  if not run_all_tests(args.keep_open):
    if not args.force:
      print("ERROR: Tests failed, not continuing.")
      sys.exit(1)
    else:
      print("WARNING: Tests failed, but continuing anyway.")

  if args.containerized:
    teardown_container(xvfb)

  # Run the dev server.
  if not args.test_only:
    print("Starting dev server...")

    # Enable MCU simulation if necessary.
    settings = {}
    if args.module_simulation:
      sim = simulator.Simulator()
      settings["mcu_serial"] = sim.get_serial_name()

      # We always have at least the base module.
      sim.add_module(base_module.BaseModule)

      # Start the simulator running.
      sim.start()

    server.main(dev_mode=(not args.production), override_settings=settings)


if __name__ == "__main__":
  main()