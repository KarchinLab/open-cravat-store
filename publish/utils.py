import os
import yaml
import re
import functools
import sqlite3
import hashlib
import secrets
from cravat import store_utils as su
from distutils.version import LooseVersion
import smtplib
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import email_templates
import sys
import time

email_re = re.compile('^[^@]+@[^@]+\.[^@]+$')

def get_config():
    default_path = os.path.join(os.path.dirname(__file__),'config.yml')
    config_path = os.environ.get('CRAVATSTORE_CONFIG_PATH',
                                 default_path)
    if not(os.path.exists(config_path)):
           config_path = default_path
    return yaml.safe_load(open(config_path).read())
conf = get_config()


def get_dbconn():
    db_path = conf['db_path']
    dbconn = sqlite3.connect(db_path)
    return dbconn
dbconn = get_dbconn()

def create_user(username, password):
    cursor = dbconn.cursor()
    ps_hash, salt = salt_hash_password(password)
    q = 'insert into users (username, ps_hash, salt) '\
        +'values ("%s", "%s", "%s");' \
        %(username, ps_hash, salt)
    cursor.execute(q)
    cursor.close()
    dbconn.commit()

def email_verified(username):
    cursor = dbconn.cursor()
    q = 'select email_verified from users where username="%s";' %username
    cursor.execute(q)
    r = cursor.fetchone()
    cursor.close()
    return r is not None and r[0] == 'true'
    
def password_correct(username, password):
    if not(isinstance(username,str)) or not(isinstance(password,str)):
        return False
    cursor = dbconn.cursor()
    q = 'select ps_hash, salt from users where username="%s";' %username
    cursor.execute(q)
    r = cursor.fetchone()
    cursor.close()
    correct_pw = False
    if r is not None:
        ps_hash, salt = salt_hash_password(password, salt=r[1])
        correct_pw = ps_hash == r[0]
    return correct_pw
    
def user_exists(username):
    cursor = dbconn.cursor()
    q = 'select count(*) from users where username="%s";' %username
    cursor.execute(q)
    r = cursor.fetchone()
    cursor.close()
    return r[0] > 0

def change_password(username, new_pw):
    cursor = dbconn.cursor()
    ps_hash, salt = salt_hash_password(new_pw)
    q = 'update users set ps_hash="%s", salt="%s" where username="%s";' \
        %(ps_hash, salt, username)
    cursor.execute(q)
    if cursor.rowcount > 0:
        cursor.close()
        dbconn.commit()
        return new_pw
    else:
        cursor.close()
        dbconn.commit()
        return None
    
def salt_hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex()
    ps = password + salt
    ps_hash = hash_string(ps)
    return ps_hash, salt
        
def hash_string(s, constructor=hashlib.sha256):
    hasher = constructor()
    hasher.update(s.encode())
    return hasher.hexdigest()
    
def correct_module_developer(module_name, username):
    cursor = dbconn.cursor()
    q = 'select developer from modules where module_name="%s";' %module_name
    cursor.execute(q)
    r = cursor.fetchone()
    cursor.close()
    correct = True
    if r is not None:
        correct = username == r[0]
    return correct

def module_exists(module_name, version=None):
    cursor = dbconn.cursor()
    q = 'select * from modules where module_name="%s";' %module_name
    cursor.execute(q)
    r = cursor.fetchone()
    cursor.close()
    if r is not None:
        if version is not None:
            return version in get_current_versions(module_name)
        else:
            return True
    else:
        return False

def assign_module(module_name, username):
    cursor = dbconn.cursor()
    q = 'insert or replace into modules (module_name, developer) values ('\
        +'"%s", ' %module_name\
        +'"%s"' %username\
        +');'
    cursor.execute(q)
    success = cursor.rowcount > 0
    cursor.close()
    dbconn.commit()
    return success

def get_manifest():
    final_dir = conf['final_dir']
    path_builder = su.PathBuilder(final_dir, 'file')
    manifest_path = path_builder.manifest_nover()
    if os.path.exists(manifest_path):
        for _ in range(5):
            try:
                manifest = yaml.safe_load(open(manifest_path))
                break
            except:
                print('Error fetching manifest')
                time.sleep(0.2)
                continue
        if manifest is None: manifest = {}
    else:
        manifest = {}
    return manifest

def get_current_versions(module_name):
    manifest = get_manifest()
    try:
        module_info = manifest[module_name]
    except KeyError:
        return []
    return module_info['versions']

def get_latest_version(module_name):
    manifest = get_manifest()
    try:
        module_info = manifest[module_name]
    except KeyError:
        return '0'
    return module_info['latest_version']


def generate_temp_token(username, type):
    if type not in ['reset','verify']:
        raise Exception('Invalid temp token type: %s' %type)
    cursor = dbconn.cursor()
    max_attempts = 100
    attempts = 0
    while attempts < max_attempts:
        attempts += 1
        token = secrets.token_urlsafe()
        q = 'insert into temp_links (username, type, token) '\
            +'values ("%s","%s","%s");' %(username, type, token)
        try:
            cursor.execute(q)
            if cursor.rowcount > 0:
                cursor.close()
                dbconn.commit()
                return token
            else:
                cursor.close()
                return None
        except sqlite3.IntegrityError:
            continue
    cursor.close()
    return None

def reset_link_hit(token):
    cursor = dbconn.cursor()
    q = 'select username from temp_links where type="reset" and token="%s";' %token
    cursor.execute(q)
    r = cursor.fetchone()
    cursor.close()
    if r is not None:
        username = r[0]
        verify_email(username)
        newpw = reset_password(username)
        return newpw
    else:
        return None

def reset_password(username):
    newpw = secrets.token_urlsafe(8)
    newpw = change_password(username, newpw)
    if newpw:
        cursor = dbconn.cursor()
        q = 'delete from temp_links where type="reset" and username="%s";' %username
        cursor.execute(q)
        cursor.close()
    return newpw
    
def verify_link_hit(token):
    cursor = dbconn.cursor()
    q = 'select username from temp_links where type="verify" and token="%s";' %token
    cursor.execute(q)
    r = cursor.fetchone()
    cursor.close()
    success = False
    if r is not None:
        username = r[0]
        success = verify_email(username)
    return success
    
def verify_email(username):
    cursor = dbconn.cursor()
    q = 'update users set email_verified="true" where username="%s";' %username
    cursor.execute(q)
    if cursor.rowcount > 0:
        q = 'delete from temp_links where username="%s" and type="verify";' %username
        cursor.execute(q)
        cursor.close()
        return True
    else:
        cursor.close()
        return False

def get_smtpconn():
    sender = conf['email_sender']
    server_address = conf['smtp_address']
    server = smtplib.SMTP(server_address)
    server.ehlo()
    return sender, server

def create_html_email(sender,recipients,subject,text,html):
    msg = MIMEMultipart('alternative')
    msg['From'] = sender
    msg['To'] = ', '.join(recipients)
    msg['Subject'] = subject
    part1 = MIMEText(text,'plain')
    msg.attach(part1)
    part2 = MIMEText(html,'html')
    msg.attach(part2)
    return msg

def send_reset_email(username, base_url):
    cursor = dbconn.cursor()
    q = 'select count(*) from users where username="%s";' %username
    cursor.execute(q)
    r = cursor.fetchone()
    cursor.close()
    if r[0] == 0:
        return None
    
    sender, server = get_smtpconn()
    
    token = generate_temp_token(username, 'reset')
    link = base_url+'/resetlink/'+token
    text=email_templates.reset_text.format(link)
    html=email_templates.reset_html.format(link)
    msg = create_html_email(sender,
                            [username],
                            email_templates.reset_subject,
                            text,
                            html)
    server.send_message(msg)
    server.close()
    
def send_module_completed_email(module_name, version, success):
    cursor = dbconn.cursor()
    q = 'select developer from modules where module_name="%s";' %module_name
    cursor.execute(q)
    r = cursor.fetchone()
    cursor.close()
    if r is not None:
        developer_email = r[0]
    else:
        return None
    
    sender, server = get_smtpconn()
    if success:
        subject = email_templates.publish_success_subject
        text_template = email_templates.publish_success_text
        html_template = email_templates.publish_success_html
    else:
        subject = email_templates.publish_fail_subject
        text_template = email_templates.publish_fail_text
        html_template = email_templates.publish_fail_html
        
    text = text_template.format(module_name, version)
    html = html_template.format(module_name, version)
    msg = create_html_email(sender,
                            [developer_email],
                            subject,
                            text,
                            html)
    server.send_message(msg)
    server.close()

def send_verify_email(username, base_url):
    sender, server = get_smtpconn()
    
    token = generate_temp_token(username,'verify')
    link = base_url+'/verifylink/'+token
    text=email_templates.verify_text.format(link)
    html=email_templates.verify_html.format(link)
    msg = create_html_email(sender,
                            [username],
                            email_templates.verify_subject,
                            text,
                            html)
    server.send_message(msg)
    server.close()
    
def log(*args):
    print(*args)
    sys.stdout.flush()

def initialize_db():
    cursor = dbconn.cursor()

    # Create tables if not exists
    q = 'create table if not exists users ('\
        +'username text primary key, '\
        +'ps_hash text not null, '\
        +'salt text not null, '\
        +'email_verified text default "false"'\
        +');'
    cursor.execute(q)
    q = 'create table if not exists modules ('\
        +'module_name text primary key, '\
        +'developer text references users (username)'\
        +');'
    cursor.execute(q)
    q = 'create table if not exists temp_links ('\
        +'token text primary key , '\
        +'type text not null, '\
        +'username text references users (username)'\
        +');'
    cursor.execute(q)
    cursor.close()

    # Create admin user
    admin_user = conf['admin_user']
    admin_pw = conf['admin_pw']
    if not(user_exists(admin_user)):
        create_user(admin_user, admin_pw)
        log('create admin user')
    elif not(password_correct(admin_user, admin_pw)):
        change_password(admin_user, admin_pw)

    return True
