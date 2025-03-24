#!/usr/bin/env python
import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

from app.config import SandboxSettings
from app.logger import logger
from app.sandbox.client import SANDBOX_CLIENT


async def check_docker():
    """Check if Docker is available and running"""
    try:
        # Check if Docker is installed
        process = subprocess.run(
            ["docker", "--version"], capture_output=True, text=True
        )
        if process.returncode != 0:
            logger.error("Docker is not installed. Please install Docker first.")
            return False

        logger.info(f"Docker version: {process.stdout.strip()}")

        # Check if Docker is running
        process = subprocess.run(["docker", "info"], capture_output=True, text=True)
        if process.returncode != 0:
            logger.error("Docker is not running. Please start Docker and try again.")
            logger.info("On macOS, you can start Docker by running `open -a Docker`")
            return False

        logger.info("Docker is running properly")
        return True

    except FileNotFoundError:
        logger.error("Docker command not found. Please install Docker.")
        return False


async def wait_for_docker(max_retries=3, retry_interval=5):
    """Wait for Docker to start, with retry mechanism"""
    for i in range(max_retries):
        if await check_docker():
            return True

        if i < max_retries - 1:
            logger.info(f"Waiting for Docker to start... ({i+1}/{max_retries})")
            await asyncio.sleep(retry_interval)

    return False


async def run_basic_test():
    """Run basic sandbox tests"""
    logger.info("Starting basic sandbox test")

    try:
        # Create sandbox environment
        logger.info("Creating sandbox environment...")

        # Use custom configuration
        sandbox_config = SandboxSettings(
            use_sandbox=True,
            image="python:3.12-slim",
            work_dir="/workspace",
            memory_limit="512m",
            cpu_limit=1.0,
            timeout=60,
            network_enabled=True,
        )

        await SANDBOX_CLIENT.create(config=sandbox_config)

        # Test file writing
        test_content = """
print("Hello from sandbox!")
import platform
import sys
print(f"Python version: {platform.python_version()}")
print(f"Platform: {platform.platform()}")
print(f"Sys path: {sys.path}")
"""
        logger.info("Testing file writing...")
        await SANDBOX_CLIENT.write_file("test_script.py", test_content)

        # Read file to confirm content
        logger.info("Reading file to confirm content...")
        file_content = await SANDBOX_CLIENT.read_file("test_script.py")
        logger.info(f"File content length: {len(file_content)} characters")

        # Execute command
        logger.info("Executing Python script...")
        result = await SANDBOX_CLIENT.run_command("python test_script.py")

        logger.info("Execution result:")
        print("-" * 60)
        print(result)
        print("-" * 60)

        # Test package installation
        logger.info("Testing package installation...")
        await SANDBOX_CLIENT.run_command(
            "pip install numpy --no-cache-dir", timeout=120
        )

        # Test using installed package
        numpy_test = """
import numpy as np
arr = np.array([1, 2, 3, 4, 5])
print(f"NumPy array: {arr}")
print(f"Mean: {np.mean(arr)}")
print(f"Sum: {np.sum(arr)}")
"""
        await SANDBOX_CLIENT.write_file("numpy_test.py", numpy_test)

        logger.info("Running NumPy test...")
        result = await SANDBOX_CLIENT.run_command("python numpy_test.py")

        logger.info("NumPy test result:")
        print("-" * 60)
        print(result)
        print("-" * 60)

        return True

    except Exception as e:
        logger.error(f"Error during test: {str(e)}")
        return False

    finally:
        # Clean up resources
        logger.info("Cleaning up sandbox resources...")
        await SANDBOX_CLIENT.cleanup()


async def test_sandbox_timeout():
    """Test sandbox timeout handling"""
    logger.info("Starting sandbox timeout test")

    try:
        # Create sandbox environment
        await SANDBOX_CLIENT.create()

        # Create a script that will cause timeout
        timeout_script = """
import time
print("Starting infinite loop...")
while True:
    print(".", end="", flush=True)
    time.sleep(1)
"""
        await SANDBOX_CLIENT.write_file("timeout_test.py", timeout_script)

        # Set a short timeout
        logger.info("Running timeout test (5 second timeout)...")
        try:
            result = await SANDBOX_CLIENT.run_command(
                "python timeout_test.py", timeout=5
            )
            logger.error(
                "Timeout test failed: Command should have timed out but didn't"
            )
        except Exception as e:
            logger.info(f"Timeout test successfully caught exception: {str(e)}")
            return True

    except Exception as e:
        logger.error(f"Error during test: {str(e)}")
        return False

    finally:
        # Clean up resources
        await SANDBOX_CLIENT.cleanup()


async def main():
    """Main function"""
    logger.info("=== Sandbox Environment Test Started ===")

    # Check if Docker is already running
    if not await wait_for_docker():
        logger.error("Docker is not ready, cannot continue testing")
        return

    # Run basic test
    basic_test_result = await run_basic_test()

    if basic_test_result:
        logger.info("Basic test passed")

        # Run timeout test
        timeout_test_result = await test_sandbox_timeout()
        if timeout_test_result:
            logger.info("Timeout test passed")
        else:
            logger.error("Timeout test failed")
    else:
        logger.error("Basic test failed")

    logger.info("=== Sandbox Environment Test Completed ===")


if __name__ == "__main__":
    asyncio.run(main())
