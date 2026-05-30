import os
import sys
from orchestrator.vibe_logger import setup_exhaustive_logging, exhaustive_log

# Mock os.fsync to simulate a disk failure
def mock_fsync(fd):
    raise OSError("Simulated Disk Full Error during fsync!")

os.fsync = mock_fsync

@exhaustive_log
def test_function():
    print("This should not finish, logging panic should kill the process.")
    return True

if __name__ == "__main__":
    print("Setting up logger...")
    log = setup_exhaustive_logging("test_panic.log")
    print("Logger setup complete. Calling test function...")
    try:
        test_function()
        print("FAIL: Process did not exit!")
        sys.exit(0) # It should not reach here!
    except SystemExit as e:
        print(f"SUCCESS: Caught SystemExit with code {e.code}")
        sys.exit(0)
