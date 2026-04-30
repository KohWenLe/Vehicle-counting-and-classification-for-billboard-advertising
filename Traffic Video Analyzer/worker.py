import importlib
import sys


MODULE_ORDER = [
    "backend.core",
    "backend.models",
    "backend.observability",
    "backend.services",
    "backend.routes",
    "backend.worker_runtime",
]

def _clear_modules():
    for module_name in list(sys.modules):
        if module_name == "backend" or module_name.startswith("backend."):
            sys.modules.pop(module_name, None)


_clear_modules()
_loaded_modules = {name: importlib.import_module(name) for name in MODULE_ORDER}

_runtime = _loaded_modules["backend.worker_runtime"]
_services = _loaded_modules["backend.services"]

AnalysisJob = _loaded_modules["backend.models"].AnalysisJob
app = _loaded_modules["backend.core"].app
db = _loaded_modules["backend.core"].db
execute_analysis = _services.execute_analysis
prune_terminal_jobs = _services.prune_terminal_jobs
analyze_with_gpt = _services.analyze_with_gpt


def _sync_runtime_dependencies():
    _runtime.execute_analysis = execute_analysis
    _runtime.prune_terminal_jobs = prune_terminal_jobs


def get_worker_id():
    return _runtime.get_worker_id()


def recover_abandoned_jobs(worker_id=None):
    _sync_runtime_dependencies()
    return _runtime.recover_abandoned_jobs(worker_id=worker_id)


def claim_next_job(worker_id=None):
    _sync_runtime_dependencies()
    return _runtime.claim_next_job(worker_id=worker_id)


def process_job(job_id, worker_id=None):
    _sync_runtime_dependencies()
    return _runtime.process_job(job_id, worker_id=worker_id)


def process_next_job(worker_id=None):
    _sync_runtime_dependencies()
    return _runtime.process_next_job(worker_id=worker_id)


def run_worker_loop(poll_interval_seconds=2, worker_id=None):
    _sync_runtime_dependencies()
    return _runtime.run_worker_loop(poll_interval_seconds=poll_interval_seconds, worker_id=worker_id)


def maybe_run_maintenance(now=None, force=False):
    _sync_runtime_dependencies()
    return _runtime.maybe_run_maintenance(now=now, force=force)


if __name__ == "__main__":
    if "--once" in sys.argv:
        maybe_run_maintenance(force=True)
        recover_abandoned_jobs(worker_id=get_worker_id())
        process_next_job(worker_id=get_worker_id())
    else:
        run_worker_loop(worker_id=get_worker_id())
