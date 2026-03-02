import asyncio
import logging

import os

logger = logging.getLogger(__name__)

async def run_obsidian_cli(*args: str, timeout: int = 10) -> tuple[int, str, str]:
    """Run an Obsidian CLI command and return (returncode, stdout, stderr)."""
    # Inherit system environment variables so electron can find the X Server / Wayland display
    # but force CLI mode so it doesn't open the full UI unnecessarily
    env = os.environ.copy()
    env["OBSIDIAN_USE_CLI"] = "1"
    
    cmd = ["obsidian", *args]
    logger.debug(f"Running Obsidian CLI command: {' '.join(cmd)}")
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        
        return (
            process.returncode or 0,
            stdout.decode("utf-8").strip(),
            stderr.decode("utf-8").strip(),
        )
    except asyncio.TimeoutError:
        logger.error(f"Obsidian CLI command timed out after {timeout}s: {' '.join(cmd)}")
        if 'process' in locals():
            try:
                process.kill()
            except ProcessLookupError:
                pass
        return 1, "", "Command timed out"
    except Exception as e:
        logger.error(f"Error running Obsidian CLI command: {e}")
        return 1, "", str(e)
