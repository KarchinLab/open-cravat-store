import zipfile
import time
from cravat import admin_util as au
from cravat import store_utils as su
import utils
import os
import shutil
import sys
import traceback
import yaml
import os
import copy
from distutils.version import LooseVersion
import sys
import datetime
import traceback
from queue import Empty
import json
import requests
from pkg_resources import Requirement

conf = utils.get_config()
uploads_dir = conf['uploads_dir']
iso8601_tfmt = '%Y-%m-%dT%H:%M:%S.%f%z'

def zip_module_code(module_name, dir, zpath):
    """
    Create a module code archive for upload at the location in zpath.
    """
    local_info = au.LocalModuleInfo(dir, name=module_name)
    zf = zipfile.ZipFile(zpath,'w')
    for item_name, item_path in list_directory(local_info.directory):
        item_path = os.path.join(local_info.directory, item_name)
        if item_path != local_info.data_dir:
            su.add_to_zipfile(item_path, zf, start=local_info.directory)
                
def zip_module_data(module_name, dir, zpath):
    """
    Create a module data archive for upload at the location in zpath.
    """
    local_info = au.LocalModuleInfo(dir, name=module_name)
    zf = zipfile.ZipFile(zpath,'w')
    su.add_to_zipfile(local_info.data_dir, zf, start=local_info.directory)
    
def clear_directory(dpath):
    for _, item_path in list_directory(dpath):
        if os.path.isdir(item_path):
            shutil.rmtree(item_path)
        else:
            os.remove(item_path)
            
def list_directory(dpath):
    for item_name in os.listdir(dpath):
        yield item_name, os.path.join(dpath, item_name)
        
def unzipped_size(zf_path):
    zf = zipfile.ZipFile(zf_path)
    size = 0
    for zi in zf.infolist(): size += zi.file_size
    return size

class MetaModule (object):
    def __init__(self, path_builder, mname):
        self._pb = path_builder
        self.name = mname
        self._mdir = self._pb.module_dir(self.name)
        self.modules = {}
        self._versions = []
        for version in os.listdir(self._mdir):
            module = Module(self._pb, self.name, version)
            if module.private:
                continue
            self.modules[version] = module
            self._versions.append(version)
            self._versions.sort(key=LooseVersion)
    
    def get_versions(self, ocrv_version=None):
        if ocrv_version:
            match_vers = []
            for v in self._versions:
                module = self.modules[v]
                if ocrv_version in module.ocrv_req:
                    match_vers.append(v)
            return match_vers
        else:
            return self._versions
    
    def get_dataversions(self, versions=[]):
        if not versions:
            versions = self._versions
        data_versions = {}
        for i, version in enumerate(versions):
            module = self.modules[version]
            if module.has_data:
                data_versions[version] = version
            elif i == 0:
                data_versions[version] = None
            else:
                data_versions[version] = data_versions[versions[i-1]]
        return data_versions

class Module (object):
    def __init__(self, path_builder, mname, version):
        self._pb = path_builder
        self.name = mname
        self.version = version
        self._mdir = self._pb.module_version_dir(self.name, self.version)
        self._code_path = self._pb.module_code(self.name, self.version)
        self.code_size = unzipped_size(self._code_path)
        self._data_path = self._pb.module_data(self.name, self.version)
        self.has_data = os.path.exists(self._data_path)
        self.data_size = unzipped_size(self._data_path) if self.has_data else 0
        self.size = self.code_size + self.data_size
        self._conf_path = self._pb.module_conf(self.name, self.version)
        self._conf = yaml.safe_load(open(self._conf_path))
        self.ocrv_req = Requirement('blank'+self._conf.get('requires_opencravat',''))
        self.requires = self._conf.get('requires',None)
        self.title = self._conf['title']
        self.type = self._conf['type']
        self.developer = self._conf['developer']
        self.description = self._conf['description']
        self.tags = self._conf.get('tags')
        self.datasource = self._conf.get('datasource')
        self.hidden = self._conf.get('hidden', False)
        self.private = self._conf.get('private', False)
        self.groups = self._conf.get('groups',[])
        self.commercial_warning = self._conf.get('commercial_warning')
        self.has_logo = os.path.exists(self._pb.module_logo(self.name, self.version))
        self._metainfo = {}
        self.publish_dts = None
        self._meta_path = self._pb.module_meta(self.name, self.version)
        if os.path.exists(self._meta_path):
            self._metainfo = yaml.safe_load(open(self._meta_path))
            self.publish_dts = self._metainfo.get('publish_time')
        if self.publish_dts is None:
            publish_dt = datetime.datetime.fromtimestamp(os.path.getmtime(self._code_path))
            publish_dt.replace(tzinfo=datetime.timezone.utc)
            self.publish_dts = publish_dt.strftime(iso8601_tfmt)


def build_manifest():
    global conf
    final_dir = conf['final_dir']
    path_builder = su.PathBuilder(final_dir, 'file')
    modules_dir = os.path.join(final_dir,'modules')
    metamodules = {}
    for mname in os.listdir(modules_dir):
        try:
            metamodules[mname] = MetaModule(path_builder, mname)
        except:
            utils.log(traceback.format_exc())
            continue
    pkg_versions = au.get_package_versions()
    pkg_versions.append(None)
    for pkg_version in pkg_versions:
        manifest = {}
        for mname, metamodule in metamodules.items():
            match_vers = metamodule.get_versions(ocrv_version=pkg_version)
            if not match_vers:
                continue
            latest_ver = match_vers[-1]
            latest_module = metamodule.modules[latest_ver]
            data_vers = metamodule.get_dataversions(versions=match_vers)
            latest_dataver = data_vers[latest_ver]
            if latest_dataver:
                latest_data_size = metamodule.modules[data_vers[latest_ver]].data_size
            else:
                latest_data_size = 0
            datasources = {v : metamodule.modules[v].datasource for v in match_vers}
            ds_vals = [metamodule.modules[v].datasource for v in match_vers]
            last_change_i = ds_vals.index(ds_vals[-1])
            last_change_ver = match_vers[last_change_i]
            last_change_date = metamodule.modules[last_change_ver].publish_dts
            manifest[metamodule.name] = {
                'title': latest_module.title,
                'type': latest_module.type,
                'developer': latest_module.developer,
                'description': latest_module.description,
                'tags': latest_module.tags,
                'datasource': latest_module.datasource,
                'hidden': latest_module.hidden,
                'versions': match_vers,
                'data_versions': data_vers,
                'latest_version': latest_ver,
                'code_size': latest_module.code_size,
                'data_size': latest_data_size,
                'size': latest_module.code_size+latest_data_size,
                'publish_time': last_change_date,
                'has_logo': latest_module.has_logo,
                'requires': latest_module.requires,
                'groups': latest_module.groups,
                'data_sources': datasources,
                'commercial_warning': latest_module.commercial_warning
                }
        if pkg_version is not None:
            manifest_wpath = path_builder.manifest(version=pkg_version)
        else:
            manifest_wpath = path_builder.manifest_nover()
        with open(manifest_wpath,'w') as wf:
            wf.write(yaml.dump(manifest, default_flow_style=False))

def delete_module(module_name, version=None):
    final_dir = conf['final_dir']
    pather = su.PathBuilder(final_dir, 'file')
    manifest_entry = yaml.safe_load(open(pather.manifest_nover()).read())[module_name]
    all_versions = manifest_entry['versions']
    if version is None or (len(all_versions) == 1 and all_versions[0] == version):
        module_dir = pather.module_dir(module_name)
        shutil.rmtree(module_dir)
    else:
        mver_dir = pather.module_version_dir(module_name, version)
        if version != all_versions[-1]:
            next_version = all_versions[all_versions.index(version)+1]
            next_data_version = manifest_entry['data_versions'][next_version]
            if next_data_version == version:
                shutil.copy(pather.module_data(module_name, version),
                            pather.module_data(module_name, next_version)
                            )
                shutil.copy(pather.module_data_manifest(module_name, version),
                            pather.module_data_manifest(module_name, next_version)
                            )
        shutil.rmtree(mver_dir)
            
def handle_queues(publish_queue, delete_queue):
    utils.log('Crawler started at pid %d' %os.getpid())
    sys.stdout.flush()
    modules_published = []
    modules_deleted = []
    while True:
        # Publish queue
        try:
            module_name, version, archive_path, manifest_path = publish_queue.get(True, 2)
            utils.log(f'Crawler: publish {module_name}:{version} from {archive_path}')
            publish_module(module_name, version, archive_path, manifest_path)
            os.remove(archive_path)
            os.remove(manifest_path)
            modules_published.append((module_name, version))
            continue
        except Empty:
            pass
        except KeyboardInterrupt:
            raise
        except:
            utils.log(traceback.format_exc())
            utils.log(f'Crawler: send failure email for {module_name}:{version}')
            utils.send_module_completed_email(module_name, version, False)
            continue
        # Delete queue
        try:
            args, kwargs = delete_queue.get(True, 2)
            module_name = args[0]
            version = kwargs.get('version','all')
            utils.log(f'Crawler: delete {module_name}:{version}')
            delete_module(*args, **kwargs)
            modules_deleted.append((module_name, version))
            continue
        except Empty:
            pass
        except KeyboardInterrupt:
            raise
        # Rebuild manifest when action(s) taken
        if modules_published or modules_deleted:
            utils.log('Crawler: rebuild manifest')
            build_manifest()
            utils.log('Crawler: manifest finished')
            for module_name, version in modules_published:
                utils.log(f'Crawler: send success email for {module_name}:{version}')
                utils.send_module_completed_email(module_name, version, True)
            modules_published = []
            modules_deleted = []
    
def publish_module(module_name, version, archive_path, manifest_path):
    # Unpack to temp location
    temp_dir = conf['temp_dir']
    temp_path_builder = su.PathBuilder(temp_dir,'file')
    temp_mver_dir = temp_path_builder.module_version_dir(module_name, version)
    try:
        os.makedirs(temp_mver_dir)
    except OSError:
        clear_directory(temp_mver_dir)
    zf = zipfile.ZipFile(archive_path)
    zf.extractall(temp_mver_dir)
    zf.close()
    manifest = au.load_yml_conf(manifest_path)
    correct = su.verify_against_manifest(temp_mver_dir, manifest)
    # Repackage and move to final dir
    if correct:
        local_info = au.LocalModuleInfo(temp_mver_dir, name=module_name)
        final_dir = conf['final_dir']
        # PathBuilder is used to put files in correct location
        path_builder = su.PathBuilder(final_dir,'file')
        mver_dir = path_builder.module_version_dir(module_name, version)
        try:
            os.makedirs(mver_dir)
        except OSError:
            pass
        # Zip code
        code_zf_path = path_builder.module_code(module_name, version)
        zip_module_code(module_name, temp_mver_dir, code_zf_path)
        # Extract and write code portion of module manifest
        code_manifest_path = path_builder.module_code_manifest(module_name, version)
        code_manifest = copy.deepcopy(manifest)
        if 'data' in code_manifest:
            del code_manifest['data'] 
        with open(code_manifest_path,'w') as wf:
            yaml.dump(code_manifest, wf, default_flow_style=False)
        # Zip data if it exists
        if local_info.data_dir_exists:
            data_zf_path = path_builder.module_data(module_name, version)
            zip_module_data(module_name, temp_mver_dir, data_zf_path)
            # Write a data manifest
            data_manifest_path = path_builder.module_data_manifest(module_name, version)
            data_manifest = {'data':manifest['data']}
            with open(data_manifest_path,'w') as wf:
                yaml.dump(data_manifest, wf, default_flow_style=False)
        # Copy conf outside of zip
        if local_info.conf_exists:
            shutil.copy(local_info.conf_path, path_builder.module_conf(module_name, version))
        # Copy readme outside of zip
        if local_info.readme_exists:
            shutil.copy(local_info.readme_path, path_builder.module_readme(module_name, version))
        # Copy images outside of zip
        for temp_root, _, files in os.walk(temp_mver_dir):
            rel_temp_root = os.path.relpath(os.path.abspath(temp_root), start=os.path.abspath(temp_mver_dir))
            final_root = os.path.join(mver_dir,rel_temp_root)
            for fname in files:
                file_extension = fname.split('.')[-1]
                if file_extension in ['png','jpg']:
                    try:
                        os.makedirs(final_root)
                    except OSError:
                        pass
                    temp_fpath = os.path.join(temp_root, fname)
                    final_fpath = os.path.join(final_root, fname)
                    shutil.copy(temp_fpath, final_fpath)
        # Write metainfo
        metainfo = {}
        # Upload time
        upload_time = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
        metainfo['publish_time'] = upload_time.strftime(iso8601_tfmt)
        with open(path_builder.module_meta(module_name, version),'w') as wf:
            wf.write(yaml.dump(metainfo, default_flow_style=False))
    else:
        raise Exception('Module manifest check failed')
    return correct
    
if __name__ == '__main__':
    archive_path = sys.argv[1]
    module_name, version = sys.argv[2].split(':')
