import os
import subprocess
from typing import Dict, List, Optional

from app.config import config
from app.logger import logger
from app.sandbox.client import SANDBOX_CLIENT
from app.tool.base import BaseTool, ToolResult


class SandboxPythonExecute(BaseTool):
    """
    A tool for executing Python code in a secure sandbox environment.

    This tool uses Docker to create an isolated environment for code execution,
    providing security and preventing malicious code from affecting the host system.
    """

    name: str = "sandbox_python_execute"
    description: str = (
        "Executes Python code in a secure sandbox environment. "
        "The code runs in an isolated Docker container with limited resources. "
        "Use this for safely executing untrusted or experimental code. "
        "Only print outputs are captured - use print statements to see results. "
        "After execution, use the terminate tool to end the session."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "The Python code to execute in the sandbox.",
            },
            "timeout": {
                "type": "integer",
                "description": "Execution timeout in seconds (default: 30).",
                "default": 30,
            },
            "install_packages": {
                "type": "string",
                "description": "Optional comma-separated list of pip packages to install before execution.",
                "default": "",
            },
            "allow_network": {
                "type": "boolean",
                "description": "Whether to allow network access in the sandbox (default: false).",
                "default": False,
            },
            "auto_terminate": {
                "type": "boolean",
                "description": "Whether to automatically terminate the session after execution (default: false).",
                "default": False,
            },
        },
        "required": ["code"],
    }

    # Track installed packages to avoid reinstalling
    _installed_packages: List[str] = []

    async def execute(
        self,
        code: str,
        timeout: int = 30,
        install_packages: str = "",
        allow_network: bool = False,
        auto_terminate: bool = False,
    ) -> ToolResult:
        """
        Executes the provided Python code in a sandbox with a timeout.

        Args:
            code (str): The Python code to execute.
            timeout (int): Execution timeout in seconds (default: 30).
            install_packages (str): Optional comma-separated list of pip packages to install.
            allow_network (bool): Whether to allow network access (default: False).
            auto_terminate (bool): Whether to automatically terminate the session after execution (default: False).

        Returns:
            ToolResult: Contains execution output or error message.
        """
        try:
            # Create a unique filename for the code
            script_filename = "execution_script.py"

            # Ensure sandbox is initialized with proper network settings
            if not SANDBOX_CLIENT.sandbox:
                logger.info("Initializing sandbox for code execution")
                sandbox_config = config.sandbox
                # Override network setting based on parameter
                sandbox_config.network_enabled = allow_network
                await SANDBOX_CLIENT.create(config=sandbox_config)

            # Install packages if specified
            if install_packages:
                packages = [
                    pkg.strip() for pkg in install_packages.split(",") if pkg.strip()
                ]
                # Only install packages that haven't been installed yet
                packages_to_install = [
                    pkg for pkg in packages if pkg not in self._installed_packages
                ]

                if packages_to_install:
                    logger.info(
                        f"Installing packages: {', '.join(packages_to_install)}"
                    )
                    install_cmd = (
                        f"pip install {' '.join(packages_to_install)} --no-cache-dir"
                    )
                    try:
                        install_result = await SANDBOX_CLIENT.run_command(
                            install_cmd, timeout=120
                        )
                        # Add successfully installed packages to our tracking list
                        self._installed_packages.extend(packages_to_install)
                        logger.info(f"Package installation output: {install_result}")
                    except Exception as e:
                        return ToolResult(
                            output=f"Error installing packages: {str(e)}\nExecution terminated. Please check package names or try increasing timeout.\nPlease use the terminate tool to end the session.",
                            error=str(e),
                        )

            # Write code to file in sandbox
            await SANDBOX_CLIENT.write_file(script_filename, code)

            # Execute the code
            logger.info(f"Executing code in sandbox with timeout {timeout}s")
            command = f"python {script_filename}"
            result = await SANDBOX_CLIENT.run_command(command, timeout=timeout)

            # Build complete output message
            output_message = (
                f"Code execution completed successfully! Output:\n\n"
                f"{result}\n\n"
                f"Execution environment: Docker sandbox (Python)\n"
                f"Timeout setting: {timeout} seconds\n"
                f"Network access: {'Enabled' if allow_network else 'Disabled'}\n"
            )

            output_message += "\nTask completed. To execute other code, please send a new request; if no further tasks, use the terminate tool to end the session."

            return ToolResult(output=output_message)

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error executing code in sandbox: {error_msg}")

            if "timeout" in error_msg.lower():
                return ToolResult(
                    output=f"Execution timed out after {timeout} seconds. The code might be too complex, contain infinite loops, or require more time to complete. Please modify the code or increase the timeout.\nPlease use the terminate tool to end the session.",
                    error=f"Timeout after {timeout}s",
                )

            return ToolResult(
                output=f"Error executing code: {error_msg}\nPlease use the terminate tool to end the session.",
                error=error_msg,
            )
        finally:
            # If auto_terminate is set, clean up resources
            if auto_terminate:
                await self.reset_sandbox()

    @classmethod
    async def reset_sandbox(cls):
        """Reset the sandbox environment, clearing all installed packages and files."""
        if SANDBOX_CLIENT.sandbox:
            await SANDBOX_CLIENT.cleanup()
            cls._installed_packages = []
            logger.info("Sandbox has been reset")
