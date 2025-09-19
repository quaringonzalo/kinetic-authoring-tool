# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import csv
import os
import subprocess
import argparse
import json
from datetime import datetime
import time
import urllib.parse
import asyncio
import logging

import aiopg
import psycopg2
from prometheus_client import start_http_server,  Histogram, Gauge

from kubescape import SoundscapeKube
from ingest_non_osm import import_non_osm_data, provision_non_osm_data_async

# Prometheus metric for event durations
event_duration = Histogram(
    "event_duration_seconds",
    "Duration of events",
    ["event_name"]
)
# Prometheus metric for last event occurrence
last_event_time = Gauge(
    "event_last_time",
    "Timestamp of last event occurrence",
    ["event_name"]
)

dsn_default_base = 'host=localhost '
dsn_init_default = dsn_default_base + 'dbname=postgres'
dsn_default = dsn_default_base + 'user=osm password=osm dbname=osm'

parser = argparse.ArgumentParser(description='ingestion engine for Soundscape')

# configuration of what the ingestion will do
parser.add_argument('--skipimport', action='store_true', help='skips import task', default=False)
parser.add_argument('--updatemodel', type=str, help='choose update model', choices=['imposmauto', 'importloop', 'none'], default='none')
parser.add_argument('--sourceupdate', action='store_true', help='update source data', default=True)
parser.add_argument('--telemetry', action='store_true', help='generate telemetry')

parser.add_argument('--delay', type=int, help='loop delay time', default=60 * 60 * 8)

# configuration of files, directories and necessary configuration
parser.add_argument('--extracts', type=str, default='extracts.json', help='extracts file')
parser.add_argument('--mapping', type=str, help='mapping file path', default='mapping.yml')
parser.add_argument('--imposm', type=str, help='imposm executable', default='imposm')
parser.add_argument('--where', metavar='region', nargs='+', type=str, help='area names')
parser.add_argument('--cachedir', type=str, help='imposm temp directory', default='/tmp/imposm3')
parser.add_argument('--diffdir', type=str, help='imposm diff directory', default='/tmp/imposm3_diffdir')
parser.add_argument('--pbfdir', type=str, help='pbf directory', default='.')
parser.add_argument('--expiredir', type=str, help='expired tiles directory', default='/tmp/imposm3_expiredir')
parser.add_argument('--extradatadir', type=str, help='CSV containing extra data to import')
parser.add_argument('--config', type=str, help='config file', default='config.json')
parser.add_argument('--provision', help='provision the database', action='store_true', default=False)
parser.add_argument('--dsn_init', type=str, help='postgres dsn init', default=dsn_init_default)
parser.add_argument('--dynamic_db', help='provision databases dynamically', action='store_true', default=False)
parser.add_argument('--dsn', type=str, help='postgres dsn', default=dsn_default)
parser.add_argument('--always_update', action='store_true', default=False)

parser.add_argument('--verbose', action='store_true', help='verbose')

def update_imposmauto(config):
    subprocess.run([config.imposm, 'run', '-config', config.config, '-mapping', config.mapping, '-connection', config.dsn, '-srid', '4326', '-cachedir', config.cachedir, '-diffdir', config.diffdir, '-expiretiles-dir', config.expiredir, '-expiretiles-zoom', '16'], check=True)

def fetch_extract(config, url):
    #
    # a local PBF may already be present
    #

    #
    # N.B. wget won't overwrite data unless it's in timestamp mode
    #

    local_pbf = os.path.join(config.pbfdir, os.path.basename(url))

    try:
        before_token = os.path.getmtime(local_pbf)
    except OSError:
        before_token = None

    try:
        # Use subprocess with DEVNULL to completely suppress wget output
        with open(os.devnull, 'w') as devnull:
            subprocess.run(['wget', '-N', '-q', url, '--directory-prefix', config.pbfdir], 
                          stdout=devnull, stderr=devnull, check=True)
        after_token = os.path.getmtime(local_pbf)
    except Exception:
        raise

    if before_token == after_token:
        return False
    else:
        return True

def fetch_extracts(config, extracts):
    start = datetime.utcnow()
    fetched = False
    for i, e in enumerate(extracts, 1):
        fetched_extract = fetch_extract(config, e['url'])
        if fetched_extract:
            pass
        else:
            pass
        fetched = fetched or fetched_extract
    elapsed = datetime.utcnow() - start
    end = datetime.utcnow()
    telemetry_log('fetch_extracts', start, end)
    return fetched

def import_extract(config, extract, incremental):
    pbf = os.path.join(config.pbfdir, os.path.basename(extract['url']))
    start = datetime.utcnow()
    
    imposm_args = [config.imposm, 'import', '-mapping', config.mapping, '-read', pbf, '-cachedir', config.cachedir]
    if incremental:
        imposm_args.extend(['-diff', '-diffdir', config.diffdir])
    
    subprocess.run(imposm_args, check=True)
    end = datetime.utcnow()
    telemetry_log('import_extract', start, end)

def import_write(config, incremental):
    start = datetime.utcnow()
    imposm_args = [config.imposm, 'import', '-mapping', config.mapping, '-write', '-connection', config.dsn, '-srid', '4326', '-cachedir', config.cachedir]
    if incremental:
        imposm_args.extend(['-diff', '-diffdir', config.diffdir])
    subprocess.run(imposm_args, check=True)
    end = datetime.utcnow()
    telemetry_log('import_write', start, end, {'dsn': config.dsn})

def import_rotate(config, incremental):
    start = datetime.utcnow()
    imposm_args = [config.imposm, 'import', '-mapping', config.mapping, '-connection', config.dsn, '-srid', '4326', '-deployproduction', '-cachedir', config.cachedir]

    if incremental:
        imposm_args.extend(['-diff', '-diffdir', config.diffdir])
    subprocess.run(imposm_args, check=True)
    end = datetime.utcnow()
    telemetry_log('import_rotate', start, end, {'dsn': config.dsn})

def import_extracts(config, extracts, incremental):
    imported = {}
    for e, i in zip(extracts, range(len(extracts))):
        if i == 0:
            cache = '-overwritecache'
        else:
            cache = '-appendcache'
        urlbits = urllib.parse.urlsplit(e['url'])
        pbf = os.path.basename(urlbits.path)
        if pbf in imported:
            continue
        imported[pbf] = True
        import_extract(config, pbf, cache, incremental)

def import_extracts_and_write(config, extracts, incremental):
    import_extracts(config, extracts, incremental)
    import_write(config, incremental)
    import_rotate(config, incremental)

async def provision_database_async(postgres_dsn, osm_dsn):
    async with aiopg.connect(dsn=postgres_dsn) as conn:
        cursor = await conn.cursor()
        try:
            await cursor.execute('CREATE DATABASE osm')
        except psycopg2.ProgrammingError:
            pass
    async with aiopg.connect(dsn=osm_dsn) as conn:
        cursor = await conn.cursor()
        await cursor.execute('CREATE EXTENSION IF NOT EXISTS postgis')
        await cursor.execute('CREATE EXTENSION IF NOT EXISTS hstore')

        # The non_osm_data table needs to exist regardless of whether we
        # have extra data to load, because the soundscape_tile query expects
        # it to exist.
        await provision_non_osm_data_async(osm_dsn)

async def provision_database_soundscape_async(osm_dsn):
    ingest_path = os.environ['INGEST']
    async with aiopg.connect(dsn=osm_dsn) as conn:
        cursor = await conn.cursor()
        with open(ingest_path + '/' + 'postgis-vt-util.sql', 'r') as sql:
            await cursor.execute(sql.read())
        with open(ingest_path + '/' + 'tilefunc.sql', 'r') as sql:
            await cursor.execute(sql.read())

def provision_database(postgres_dsn, osm_dsn):
    start = datetime.utcnow()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(provision_database_async(postgres_dsn, osm_dsn))
    end = datetime.utcnow()
    telemetry_log('provision_database', start, end, {'dsn': postgres_dsn})

def provision_database_soundscape(osm_dsn):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(provision_database_soundscape_async(osm_dsn))

def execute_kube_updatemodel_provision_and_import(config, updated):
    namespace = os.environ['NAMESPACE']
    kube = SoundscapeKube(None, namespace)
    kube.connect()

    for d in kube.enumerate_databases():
        dbstatus = d['dbstatus']

        if dbstatus == None or dbstatus == 'INIT':
            try:
                kube.set_database_status(d['name'], 'PROVISIONING')
                dsn = d['dsn2']
                dsn_init = d['dsn2'].replace('dbname=osm', 'dbname=postgres')
                provision_database(dsn_init, dsn)
                kube.set_database_status(d['name'], 'PROVISIONED')
            except Exception:
                kube.set_database_status(d['name'], 'INIT')

    if updated:
        import_extracts(config, osm_extracts, False)

    for d in kube.enumerate_databases():
        dbstatus = d['dbstatus']

        if dbstatus != 'PROVISIONED' and dbstatus != 'HASMAPDATA':
            continue

        if dbstatus == 'HASMAPDATA' and not updated:
            continue

        try:
            args.dsn = kube.get_url_dsn(d['dsn2']) #+ '?sslmode=require'
            import_write(config, False)
            import_rotate(config, False)
            if config.extradatadir:
                import_non_osm_data(config.extradatadir, d['dsn2'], logger)
            provision_database_soundscape(d['dsn2'])
            # kubernetes connection may have expired
            retry_count = 5
            while True:
                if retry_count == 0:
                    kube.set_database_status(d['name'], 'HASMAPDATA')
                    break
                else:
                    try:
                        kube.set_database_status(d['name'], 'HASMAPDATA')
                        break
                    except Exception:
                        retry_count -= 1
        except Exception:
            pass

def execute_kube_sync_deployments(manager, desc):
    seen_dbs = []
    for db in manager.enumerate_ready_databases():
        seen_dbs.append(db['name'])

        if not manager.exist_deployment_for_db(db):
            try:
                manager.create_deployment_for_db(db)
            except Exception:
                pass

    for db in manager.enumerate_deployments():
        if db['name'] not in seen_dbs:
            try:
                manager.delete_deployment_for_db(db)
            except Exception:
                pass

def execute_kube_sync_tile_services(config):
    start = datetime.utcnow()
    namespace = os.environ['NAMESPACE']
    kube = SoundscapeKube(None, namespace)
    kube.connect()

    tile_server_manager = kube.manage_tile_servers('/templates/tile-server-deployment-template')
    execute_kube_sync_deployments(tile_server_manager, 'tile service')
    end = datetime.utcnow()
    telemetry_log('sync_tile_services', start, end)

def execute_kube_sync_database_services(config):
    execute_kube_sync_tile_services(config)

def execute_kube_updatemodel(config):
    # N.B. launch tile services and metrics for already functioning databases
    #      since import of new data can/will take a while
    if config.dynamic_db:
        execute_kube_sync_database_services(config)

    rescan_delay = 60
    initial_import = True
    cycle_count = 0
    
    while True:
        cycle_count += 1
        cycle_start = datetime.utcnow()
        
        fetch_delay = config.delay
        updated = fetch_extracts(config, osm_extracts)
        if config.always_update:
            updated = True

        while fetch_delay >= 0:
            execute_kube_updatemodel_provision_and_import(config, updated or initial_import)
            updated = False
            initial_import = False

            if config.dynamic_db:
                execute_kube_sync_database_services(config)
                
            time.sleep(rescan_delay)
            fetch_delay -= rescan_delay
            
        initial_import = False

def telemetry_log(event_name, start, end, extra=None):
    if args.telemetry:
        duration = end - start
        event_duration.labels(event_name).observe(duration.total_seconds())
        last_event_time.labels(event_name).set(end.timestamp())

args = parser.parse_args()

if args.verbose:
    loglevel = logging.INFO
else:
    loglevel = logging.WARNING

if args.where or args.sourceupdate:
    extracts_f = open(args.extracts, 'r')
    osm_extracts = json.load(extracts_f)

if args.where:
    logger = logging.getLogger()
    original_count = len(osm_extracts)
    osm_extracts = list(filter(lambda e: e['name'] in args.where, osm_extracts))

logging.basicConfig(level=loglevel,
                    format='%(asctime)s:%(levelname)s:%(message)s')
logger = logging.getLogger()

if args.telemetry:
    # Start a Prometheus metrics server
    start_http_server(8000)

try:
    execute_kube_updatemodel(args)

finally:
    logging.shutdown()
