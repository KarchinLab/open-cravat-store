from pathlib import Path
import sys
import yaml
from distutils.version import LooseVersion

root = Path(sys.argv[1])
modules = root/'modules'
for moddir in modules.iterdir():
    mname = str(moddir.name)
    privacy = {}
    verdirs = {}
    for verdir in moddir.iterdir():
        version = verdir.name
        verdirs[version] = verdir
        conf_path = verdir/(mname+'.yml')
        conf = yaml.safe_load(conf_path.open())
        privacy[version] = conf.get('private',False)
    versions = [LooseVersion(v) for v in privacy.keys()]
    max_version = max(versions)
    if privacy[str(max_version)]:
        continue
    for version in privacy:
        if privacy[version] and LooseVersion(version)<max_version:
            print(verdirs[version])
        
