import importlib.util
from pathlib import Path


def test_scientific_closure_installs_windows_fcntl_compat_before_importing_closure():
    source = Path('scripts/run_r1_scientific_closure_v2.py').read_text(encoding='utf-8')
    install_at = source.find('install_fcntl_compat()')
    import_at = source.find('import run_r1_scientific_closure as closure')
    assert install_at != -1
    assert import_at != -1
    assert install_at < import_at


def test_windows_fcntl_compat_exports_required_flock_surface():
    path = Path('scripts/windows_fcntl_compat.py')
    spec = importlib.util.spec_from_file_location('windows_fcntl_compat', path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    fake = module.build_fcntl_module()
    for name in ('LOCK_EX', 'LOCK_SH', 'LOCK_UN', 'LOCK_NB', 'flock'):
        assert hasattr(fake, name)
