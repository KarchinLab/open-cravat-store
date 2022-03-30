from pathlib import Path
import sys
import yaml
from distutils.version import LooseVersion

root = Path(sys.argv[1])
modules = root/'modules'
for moddir in modules.iterdir():
    mname = str(moddir.name)
    privacy = {}
    for verdir in moddir.iterdir():
        version = verdir.name
        conf_path = verdir/(mname+'.yml')
        conf = yaml.safe_load(conf_path.open())
        privacy[version] = conf.get('private',False)
    if all(privacy.values()):
        print(moddir)
