from pathlib import Path
from .store import OracleRuntimeStore

class RuntimeStore:
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = Path.home() / ".local/share/neje-oracle/runtime_state.db"
        self._store = OracleRuntimeStore(db_path)
    
    def __getattr__(self, name):
        return getattr(self._store, name)
