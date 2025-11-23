import os
import sys
import platform
from pathlib import Path

class SingleInstanceLock:
    def __init__(self, lockfile: str = None):
        if lockfile is None:
            # Use platform-specific temp directory with app-specific name
            if platform.system() == "Windows":
                lock_dir = Path(os.environ.get("TEMP", "C:\\temp"))
            else:
                # For Railway/deployment, use /tmp or app directory
                lock_dir = Path("/tmp")
                if not lock_dir.exists():
                    # Fallback to app directory
                    lock_dir = Path(__file__).parent.parent.parent
            
            lock_dir.mkdir(exist_ok=True, parents=True)
            # Use more specific lock file name
            self.lockfile = str(lock_dir / "ora_ads_bot.lock")
        else:
            self.lockfile = lockfile
        self.fp = None
    
    def acquire(self) -> bool:
        """Acquire lock, return False if another instance is running"""
        try:
            # Check if lock file exists and process is still running
            if os.path.exists(self.lockfile):
                try:
                    with open(self.lockfile, 'r') as f:
                        old_pid = int(f.read().strip())
                    # Check if process is still running
                    if self._is_process_running(old_pid):
                        return False
                    else:
                        # Process is dead, clean up lock file
                        try:
                            os.unlink(self.lockfile)
                        except:
                            pass
                except:
                    pass
            
            self.fp = open(self.lockfile, 'w')
            
            if platform.system() == "Windows":
                # Windows: Use file locking with msvcrt if available
                try:
                    import msvcrt
                    msvcrt.locking(self.fp.fileno(), msvcrt.LK_NBLCK, 1)
                except (ImportError, OSError):
                    # Fallback: try to create exclusive lock
                    pass
            else:
                # Unix/Linux/macOS: Use fcntl
                import fcntl
                fcntl.lockf(self.fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
            
            self.fp.write(str(os.getpid()))
            self.fp.flush()
            return True
        except (IOError, OSError):
            if self.fp:
                try:
                    self.fp.close()
                except:
                    pass
                self.fp = None
            return False
    
    def _is_process_running(self, pid: int) -> bool:
        """Check if a process with given PID is still running"""
        try:
            if platform.system() == "Windows":
                try:
                    import psutil
                    return psutil.pid_exists(pid)
                except ImportError:
                    # Fallback if psutil not available
                    try:
                        import subprocess
                        result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], 
                                              capture_output=True, text=True)
                        return str(pid) in result.stdout
                    except:
                        return False
            else:
                # Unix-like systems
                os.kill(pid, 0)
                return True
        except (OSError, ProcessLookupError, ImportError):
            return False
    
    def release(self):
        """Release lock"""
        if self.fp:
            try:
                if platform.system() == "Windows":
                    try:
                        import msvcrt
                        msvcrt.locking(self.fp.fileno(), msvcrt.LK_UNLCK, 1)
                    except (ImportError, OSError):
                        pass
                else:
                    import fcntl
                    fcntl.lockf(self.fp, fcntl.LOCK_UN)
                
                self.fp.close()
                os.unlink(self.lockfile)
            except:
                pass
            finally:
                self.fp = None
    
    def __enter__(self):
        if not self.acquire():
            return None
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

# Global instance
lock = SingleInstanceLock()