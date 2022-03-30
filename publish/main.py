from aiohttp import web
import multiprocessing
from multiprocessing import Queue, Process
import os
import utils
import asyncio
from crawler import handle_queues, build_manifest
import yaml
from base64 import b64decode
import email_templates
import argparse
import sys
import time
from cravat import store_utils as su
import json

base_url = utils.conf['base_url']

upload_queue = Queue()
delete_queue = Queue()

auth_restricted_handlers = []
# admin_restricted_handlers = []

async def bodypart_to_file(bp_reader, wpath):
    """
    Writes the binary content of a BodyPartReader to a file. Writes chunks to
    avoid memory limits.
    """
    try:
        os.makedirs(os.path.dirname(wpath))
    except OSError:
        pass
    with open(wpath,'wb') as wf:
        while True:
            chunk = await bp_reader.read_chunk()
            if not(chunk):
                break
            wf.write(chunk)
            
async def write_module_manifest(bp_reader, wpath):
    manifest = await bp_reader.json()
    with open(wpath,'w') as wf:
        wf.write(yaml.dump(manifest,default_flow_style=False))
        
async def check_post_module(request):
    module_name = request.match_info['module_name']
    version = request.match_info['version']
    if not(utils.correct_module_developer(module_name, request.username)):
        err_json = su.client_error_json(su.WrongDeveloper)
        response = web.Response(status=400,text=err_json)
    elif version in utils.get_current_versions(module_name):
        err_json = su.client_error_json(su.VersionExists)
        response = web.Response(status=400,text=err_json)
    elif not(utils.email_verified(request.username)):
        utils.send_verify_email(request.username,base_url)
        err_json = su.client_error_json(su.EmailUnverified)
        response = web.Response(status=400,text=err_json)
    else:
        response = web.Response()
    return response
auth_restricted_handlers.append(check_post_module)
        
async def post_module(request):
    check_response = await check_post_module(request)
    if check_response.status != 200:
        try:
            overwrite = request.query.get('overwrite') == '1'
            version_exists = json.loads(check_response.text).get('code') == su.VersionExists.code
            if version_exists and overwrite:
                pass
            else:
                return check_response
        except:
            return check_response
    module_name = request.match_info['module_name']
    version = request.match_info['version']
    username=request.username
    uploads_dir = utils.conf['uploads_dir']
    archive_fname = '%s.%s.zip' %(module_name,version)
    archive_path = os.path.join(uploads_dir, archive_fname)
    manifest_fname = '%s.%s.manifest.yml' %(module_name, version)
    manifest_path = os.path.join(uploads_dir, manifest_fname)
    reader = await request.multipart() 
    part = await reader.next() # reads to next boundary
    while part:
        if part.name == 'manifest':
            await write_module_manifest(part, manifest_path)
        elif part.name == 'archive':
            await bodypart_to_file(part, archive_path)
        else:
            return web.Response(status=400,text=su.client_error_json(su.ClientError))
        part = await reader.next()
    upload_queue.put((module_name, version, archive_path, manifest_path))
    utils.assign_module(module_name, username)
    msg = email_templates.publish_received_text.format(module_name,
                                               version,
                                               username)
    return web.Response(body=msg)
auth_restricted_handlers.append(post_module)

@web.middleware
async def authorize_user(request, handler):
    username, password = await get_credentials(request)
    run_handler = False
    if handler in auth_restricted_handlers:
        if utils.password_correct(username, password):
            run_handler = True
            request.username = username
    else:
        run_handler = True
    if run_handler:
        resp = await handler(request)
    else:
        resp = web.Response(status=401)
    return resp

async def get_credentials(request):
    auth_header = request.headers.get('Authorization')
    if auth_header is None:
        return None, None
    else:
        auth_toks = auth_header.split()
        if auth_toks[0] != 'Basic' or len(auth_toks) < 2:
            return None, None
        else:
            credential_toks = b64decode(auth_toks[1]).decode().split(':')
            if len(credential_toks) < 2:
                return None, None
            else:
                return credential_toks[0], credential_toks[1]
            
async def create_account(request):
    d = await request.json()
    username = d['username']
    password = d['password']
    if utils.user_exists(username):
        return web.Response(status=400,body='Username is taken')
    elif not(utils.email_re.match(username)):
        return web.Response(status=400,body='Usename must be an email address')
    else:
        utils.create_user(username, password)
        utils.send_verify_email(username, base_url)
        return web.Response(body='Account created. Please check your email to verify your email address.')

async def change_password(request):
    d = await request.json()
    username = request.username
    password = d['newPassword']
    utils.change_password(username, password)
    return web.Response(body='Password changed')
auth_restricted_handlers.append(change_password)

async def check_login(request):
    return web.Response()
auth_restricted_handlers.append(check_login)

async def send_reset_email(request):
    username = request.query.get('username')
    if not(utils.user_exists(username)):
        return web.Response(status=400,body='User does not exist')
    else:
        utils.send_reset_email(username,base_url)
        return web.Response(body='Reset email sent')

async def send_verify_email(request):
    username = request.query.get('username')
    if not(utils.user_exists(username)):
        return web.Response(status=400,body='User does not exist')
    else:
        utils.send_verify_email(username,base_url)
        return web.Response(body='An email has been sent with instructions to verify your email address.')
    
async def reset_link(request):
    token = request.match_info['token']
    new_pw = utils.reset_link_hit(token)
    if new_pw is not None:
        return web.Response(body='New password: %s' %new_pw)
    else:
        return web.Response(body='Password not changed. Link may be incorrect or out of date.')
    
async def verify_link(request):
    token = request.match_info['token']
    verified = utils.verify_link_hit(token)
    if verified:
        return web.Response(body='Email is verified')
    else:
        return web.Response(body='Email not verified. Link may be incorrect or out of date.')

async def hello(request):
    return web.Response(body='The CRAVAT publish server is running here.')

async def rebuild_manifest(request):
    if request.username == utils.conf['admin_user']:
        build_manifest()
        return web.Response()
    else:
        return web.Response(status=403)
auth_restricted_handlers.append(rebuild_manifest)

async def delete_module(request):
    module_name = request.match_info['module_name']
    version = request.match_info.get('version')
    utils.log('delete module {}:{}'.format(module_name, version))
    if not(utils.module_exists(module_name, version=version)):
        err_json = su.client_error_json(su.NoSuchModule)
        response = web.Response(status=400, text=err_json)
    elif not(utils.correct_module_developer(module_name, request.username)):
        err_json = su.client_error_json(su.WrongDeveloper)
        response = web.Response(status=400,text=err_json)
    else:
        into_queue = [[module_name], {'version':version}]
        delete_queue.put(into_queue)
        module_s = module_name
        if version is not None:
            module_s += ':'+version
        msg = 'Your request if delete {} has been received. It will be deleted soon.'.format(module_s)
        response = web.Response(text=msg)
    return response
auth_restricted_handlers.append(delete_module)

if __name__ == '__main__':
    crawler = Process(target=handle_queues, args=(upload_queue, delete_queue))
    crawler.start()
    sys.stdout.flush()
    app = web.Application(middlewares=[authorize_user])
    app.router.add_get('/hello', hello)
    app.router.add_post(r'/{module_name}/{version}', post_module)
    app.router.add_delete(r'/{module_name}/{version}', delete_module)
    app.router.add_delete(r'/{module_name}', delete_module)
    app.router.add_get(r'/{module_name}/{version}/check', check_post_module)
    app.router.add_post('/create-account', create_account)
    app.router.add_post('/change-password', change_password)
    app.router.add_get('/login', check_login)
    app.router.add_post('/reset-password', send_reset_email)
    app.router.add_get(r'/resetlink/{token}', reset_link)
    app.router.add_get(r'/verifylink/{token}', verify_link)
    app.router.add_post('/verify-email', send_verify_email)
    app.router.add_post('/rebuild-manifest', rebuild_manifest)
    
    ##########################################################################
    utils.log('Checking DB')
    db_ready = utils.initialize_db()
    if db_ready:
        utils.log('Starting server')
        web.run_app(app,port=80)
    else:
        utils.log('DB check failed')
