import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import TextIO

import httpx

from eve_demo.config import DATA_DIR, ROOT


class Services:
    """Own and clean up ONLY the processes launched by this instance."""

    def __init__(
        self, api_port: int = 9100, agent_port: int = 9101, data_dir: Path | None = None
    ) -> None:
        self.api_url = f"http://127.0.0.1:{api_port}"
        self.agent_url = f"http://127.0.0.1:{agent_port}"
        self.api_port = api_port
        self.agent_port = agent_port
        self.data_dir = data_dir or DATA_DIR
        self.children: list[subprocess.Popen] = []
        self.files: list[TextIO] = []

    def __enter__(self) -> "Services":
        for port in (self.api_port, self.agent_port):
            with socket.socket() as sock:
                try:
                    sock.bind(("127.0.0.1", port))
                except OSError as exc:
                    raise RuntimeError(
                        f"Port {port} is occupied; choose --api-port/--agent-port"
                    ) from exc
        self.data_dir.mkdir(parents=True, exist_ok=True)
        env = dict(
            os.environ,
            EVE_AGENT_URL=self.agent_url,
            EVE_DATA_DIR=str(self.data_dir),
            PYTHONUNBUFFERED="1",
            PYTHONUTF8="1",
        )
        self.env = env
        try:
            for module, port in (("agent", self.agent_port), ("api", self.api_port)):
                log = open(self.data_dir / f"{module}.log", "a", encoding="utf-8")
                self.files.append(log)
                child = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        f"eve_demo.{module}:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(port),
                        "--log-level",
                        "warning",
                    ],
                    cwd=ROOT,
                    env=env,
                    stdout=log,
                    stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                self.children.append(child)
            with httpx.Client(timeout=1, trust_env=False) as http:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    if any(p.poll() is not None for p in self.children):
                        raise RuntimeError(
                            f"Service exited; inspect {self.data_dir}/agent.log and api.log"
                        )
                    try:
                        if (
                            http.get(self.api_url + "/health").is_success
                            and http.get(self.agent_url + "/.well-known/agent-card.json").is_success
                        ):
                            return self
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.2)
            raise TimeoutError("Services did not become ready in 30 seconds")
        except Exception:
            self.__exit__(None, None, None)
            raise

    def restart_supervisor(self) -> None:
        """Simulate a supervisor crash; keep the independent retrieval agent running."""
        child = self.children[-1]
        child.terminate()
        child.wait(timeout=8)
        replacement = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "eve_demo.api:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.api_port),
                "--log-level",
                "warning",
            ],
            cwd=ROOT,
            env=self.env,
            stdout=self.files[-1],
            stderr=self.files[-1],
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        self.children[-1] = replacement
        with httpx.Client(timeout=1, trust_env=False) as http:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                try:
                    if http.get(self.api_url + "/health").is_success:
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(0.2)
        raise TimeoutError("Restarted supervisor failed to become ready")

    def __exit__(self, *args) -> None:
        for child in reversed(self.children):
            if child.poll() is None:
                if sys.platform == "win32":
                    # Windows terminate() leaves MCP descendants holding inherited log handles.
                    # Only kill the process tree owned by this launcher (never by name).
                    subprocess.run(
                        ["taskkill", "/PID", str(child.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=8,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                else:
                    child.terminate()
                try:
                    child.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
        for file in self.files:
            file.close()
