#!/usr/bin/env python
import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

# Add project root to PYTHONPATH
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(current_dir)  # Assuming script is in project root
sys.path.insert(0, project_root)

from app.agent.manus import Manus
from app.logger import logger
from app.schema import AgentState
from app.tool.terminate import Terminate


async def run_sandbox_code(
    code: str, packages: str = "", timeout: int = 30, allow_network: bool = False
):
    """Run Python code in the sandbox and display the result"""
    logger.info("=== Starting sandbox Python execution ===")

    # Initialize agent
    agent = Manus()

    try:
        # Build instruction
        prompt = (
            f"Please execute the following Python code in the sandbox environment, and terminate the session immediately after completion.\n\n"
            f"{'Required packages: ' + packages if packages else ''}\n"
            f"Timeout setting: {timeout} seconds\n"
            f"Allow network access: {'Yes' if allow_network else 'No'}\n\n"
            f"```python\n{code}\n```\n\n"
            f"After execution is complete, please use the terminate tool to end the session."
        )

        logger.info("Sending execution request...")
        start_time = time.time()

        # Set maximum steps limit to prevent infinite loops
        agent.max_steps = min(agent.max_steps, 15)  # Maximum 15 steps

        # Run the agent
        result = await agent.run(prompt)

        execution_time = time.time() - start_time
        logger.info(f"Execution completed, total time: {execution_time:.2f} seconds")

        # Check agent state
        if agent.state != AgentState.FINISHED:
            logger.warning(
                "Agent did not properly terminate the session. Make sure to explicitly request termination in the prompt."
            )
            # Manually terminate
            terminate_tool = Terminate()
            await terminate_tool.execute()

        return result

    except Exception as e:
        logger.error(f"Error during execution: {str(e)}")
        return f"Execution failed: {str(e)}"


def main():
    """Parse command line arguments and run the test"""
    parser = argparse.ArgumentParser(
        description="Execute Python code in a sandbox environment"
    )
    parser.add_argument("--code", "-c", help="Python code to execute")
    parser.add_argument("--file", "-f", help="File containing Python code")
    parser.add_argument(
        "--packages", "-p", default="", help="Packages to install (comma-separated)"
    )
    parser.add_argument(
        "--timeout", "-t", type=int, default=30, help="Execution timeout (seconds)"
    )
    parser.add_argument(
        "--network", "-n", action="store_true", help="Allow network access"
    )

    args = parser.parse_args()

    # Get code
    if args.code:
        code = args.code
    elif args.file:
        try:
            with open(args.file, "r") as f:
                code = f.read()
        except Exception as e:
            logger.error(f"Failed to read file: {str(e)}")
            return
    else:
        # Interactive input
        print("Enter Python code to execute (type EOF to finish):")
        lines = []
        try:
            while True:
                line = input()
                if line.strip().lower() == "eof":
                    break
                lines.append(line)
        except EOFError:
            pass

        code = "\n".join(lines)

    if not code.strip():
        logger.error("No code provided, exiting")
        return

    # Execute code
    try:
        result = asyncio.run(
            run_sandbox_code(
                code=code,
                packages=args.packages,
                timeout=args.timeout,
                allow_network=args.network,
            )
        )
        logger.info("Execution result:")
        print("-" * 60)
        print(result)
        print("-" * 60)
    except KeyboardInterrupt:
        logger.warning("User interrupted execution")
    except Exception as e:
        logger.error(f"Execution failed: {str(e)}")


if __name__ == "__main__":
    main()
