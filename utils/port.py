"""Port utilities for finding and managing processes by port."""

import json
import os
import re
import signal
import subprocess
import time
from typing import List, Optional


class PortUtils:
    """Utilities for finding and killing processes by port."""
    
    @staticmethod
    def parse_env_file(env_path: str) -> Optional[int]:
        """Parse .env file and extract PORT value."""
        if not os.path.exists(env_path):
            return None
        
        try:
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    # Skip comments and empty lines
                    if not line or line.startswith('#'):
                        continue
                    
                    # Look for PORT=value
                    if line.startswith('PORT='):
                        port_str = line.split('=', 1)[1].strip()
                        # Remove quotes if present
                        port_str = port_str.strip('"\'')
                        try:
                            return int(port_str)
                        except ValueError:
                            continue
        except Exception:
            return None
        
        return None
    
    @staticmethod
    def parse_package_json_port(package_path: str) -> Optional[int]:
        """Parse package.json for port information in scripts."""
        if not os.path.exists(package_path):
            return None
        
        try:
            with open(package_path, 'r') as f:
                data = json.load(f)
            
            # Check scripts section for port patterns
            scripts = data.get('scripts', {})
            for script_name, script_cmd in scripts.items():
                if 'dev' in script_name.lower() or 'start' in script_name.lower():
                    # Look for port patterns like --port 3000, -p 3000, PORT=3000
                    port_patterns = [
                        r'--port[= ](\d+)',
                        r'-p[= ](\d+)',
                        r'PORT[= ](\d+)',
                        r':(\d{4,5})'  # Common port pattern like :3000
                    ]
                    
                    for pattern in port_patterns:
                        match = re.search(pattern, script_cmd, re.IGNORECASE)
                        if match:
                            try:
                                port = int(match.group(1))
                                if 1000 <= port <= 65535:  # Valid port range
                                    return port
                            except (ValueError, IndexError):
                                continue
        except Exception:
            return None
        
        return None
    
    @staticmethod
    def detect_project_port(project_path: str) -> Optional[int]:
        """Detect port from .env file or package.json."""
        # Try .env first
        env_port = PortUtils.parse_env_file(os.path.join(project_path, '.env'))
        if env_port:
            return env_port
        
        # Try .env.local
        env_local_port = PortUtils.parse_env_file(os.path.join(project_path, '.env.local'))
        if env_local_port:
            return env_local_port
        
        # Try package.json
        pkg_port = PortUtils.parse_package_json_port(os.path.join(project_path, 'package.json'))
        if pkg_port:
            return pkg_port
        
        return None
    
    @staticmethod
    def find_process_by_port(port: int) -> List[int]:
        """Find PIDs of Node.js processes listening on the given port."""
        pids = []
        try:
            # Use ss to find processes using the port, then filter for node processes
            ss_result = subprocess.run(
                ['ss', '-tulnp'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if ss_result.returncode == 0:
                # Filter for lines containing the port and node
                for line in ss_result.stdout.split('\n'):
                    if f':{port} ' in line and 'LISTEN' in line:
                        # Extract PID from the line (format varies, but PID is usually in users:(("process",pid=123,fd=4)))
                        # Look for pid= pattern
                        pid_match = re.search(r'pid=(\d+)', line)
                        if pid_match:
                            pid = int(pid_match.group(1))
                            # Verify this is a node process
                            try:
                                ps_result = subprocess.run(
                                    ['ps', '-p', str(pid), '-o', 'comm='],
                                    capture_output=True,
                                    text=True,
                                    timeout=2
                                )
                                if ps_result.returncode == 0 and 'node' in ps_result.stdout.lower():
                                    pids.append(pid)
                            except Exception:
                                # If we can't verify it's node, include it anyway
                                pids.append(pid)
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            # Fallback to grep approach with ss
            try:
                # Use ss with grep to find node processes on the specific port
                grep_result = subprocess.run(
                    f'ss -tulnp | grep ":{port} " | grep node',
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if grep_result.returncode == 0:
                    for line in grep_result.stdout.split('\n'):
                        if line.strip():
                            # Extract PID using regex
                            pid_match = re.search(r'pid=(\d+)', line)
                            if pid_match:
                                try:
                                    pids.append(int(pid_match.group(1)))
                                except ValueError:
                                    continue
            except Exception:
                # Final fallback to netstat if ss fails
                try:
                    netstat_result = subprocess.run(
                        ['netstat', '-tlnp'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if netstat_result.returncode == 0:
                        for line in netstat_result.stdout.split('\n'):
                            if f':{port} ' in line and 'LISTEN' in line:
                                parts = line.split()
                                if len(parts) >= 7:
                                    pid_part = parts[6]
                                    if '/' in pid_part and 'node' in pid_part.lower():
                                        pid_str = pid_part.split('/')[0]
                                        try:
                                            pids.append(int(pid_str))
                                        except ValueError:
                                            continue
                except Exception:
                    pass
        
        return pids
    
    @staticmethod
    def kill_processes_by_port(port: int) -> bool:
        """Kill all processes listening on the given port."""
        pids = PortUtils.find_process_by_port(port)
        success = True
        
        for pid in pids:
            try:
                # Try SIGTERM first
                os.kill(pid, signal.SIGTERM)
                
                # Wait a bit for graceful shutdown
                time.sleep(0.5)
                
                # Check if process still exists, if so, force kill
                try:
                    os.kill(pid, 0)  # Check if process exists
                    os.kill(pid, signal.SIGKILL)  # Force kill
                except ProcessLookupError:
                    pass  # Process already dead
                    
            except ProcessLookupError:
                pass  # Process already dead
            except PermissionError:
                success = False
            except Exception:
                success = False
        
        return success