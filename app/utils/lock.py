import os
import sys
import fcntl
from pathlib import Path

class SingleInstanceLock:
    def __init__(self, lockfile: str = "/tmp/ora_ads.lock"):
        self.lockfile = lockfile
        self.fp = None
    
    def acquire(self) -> bool:
        """Acquire lock, return False if another instance is running"""
        try:
            self.fp = open(self.lockfile, 'w')
            fcntl.lockf(self.fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.fp.write(str(os.getpid()))
            self.fp.flush()
            return True
        except IOError:
            return False
    
    def release(self):
        """Release lock"""
        if self.fp:
            try:
                fcntl.lockf(self.fp, fcntl.LOCK_UN)
                self.fp.close()
                os.unlink(self.lockfile)
            except:
                pass
    
    def __enter__(self):
        if not self.acquire():
            return None
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

# Global instance
lock = SingleInstanceLock()