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
    logger.info(f"Attempting to download {url} to {local_pbf}")
    
    try:
        before_token = os.path.getmtime(local_pbf)
        logger.info(f"File {local_pbf} already exists with timestamp {before_token}")
    except OSError:
        before_token = None
        logger.info(f"File {local_pbf} does not exist yet, will download")

    try:
        # Trying with fewer options and capturing output for debugging
        result = subprocess.run(['wget', '-N', url, '--directory-prefix', config.pbfdir], 
                          capture_output=True, text=True, check=False)
        
        if result.returncode != 0:
            logger.error(f"wget failed with code {result.returncode}")
            logger.error(f"wget stdout: {result.stdout}")
            logger.error(f"wget stderr: {result.stderr}")
            raise Exception(f"wget failed with code {result.returncode}: {result.stderr}")
            
        after_token = os.path.getmtime(local_pbf)
        logger.info(f"Download completed, new timestamp: {after_token}")
    except Exception as e:
        logger.error(f"Error downloading {url}: {str(e)}")
        raise

    if before_token == after_token:
        logger.info(f"File {local_pbf} was not updated (timestamps match)")
        return False
    else:
        logger.info(f"File {local_pbf} was updated")
        return True

def fetch_extracts(config, extracts):
    logger.info('Fetch extracts: START')
    start = datetime.utcnow()
    fetched = False
    for i, e in enumerate(extracts, 1):
        logger.info(f"Downloading extract {i}/{len(extracts)}: {e['name']} from {e['url']}")
        try:
            fetched_extract = fetch_extract(config, e['url'])
            if fetched_extract:
                logger.info(f"Extract {e['name']} was updated")
            else:
                logger.info(f"Extract {e['name']} was already up to date")
            fetched = fetched or fetched_extract
        except Exception as e:
            logger.error(f"Failed to download extract: {str(e)}")
    elapsed = datetime.utcnow() - start
    end = datetime.utcnow()
    telemetry_log('fetch_extracts', start, end)
    logger.info(f'Fetch extracts: DONE (elapsed time: {elapsed})')
    return fetched

def import_extract(config, extract, incremental):
    pbf = os.path.join(config.pbfdir, os.path.basename(extract['url']))
    start = datetime.utcnow()
    logger.info('Import of {0}: START (region: {1})'.format(pbf, extract['name']))
    
    imposm_args = [config.imposm, 'import', '-mapping', config.mapping, '-read', pbf, '-cachedir', config.cachedir]
    if incremental:
        imposm_args.extend(['-diff', '-diffdir', config.diffdir])
    
    subprocess.run(imposm_args, check=True)
    end = datetime.utcnow()
    telemetry_log('import_extract', start, end)
    logger.info('Import of {0}: DONE (region: {1})'.format(pbf, extract['name']))

def import_write(config, incremental):
    logger.info('Writing OSM tables: START')
    start = datetime.utcnow()
    imposm_args = [config.imposm, 'import', '-mapping', config.mapping, '-write', '-connection', config.dsn, '-srid', '4326', '-cachedir', config.cachedir]
    if incremental:
        imposm_args.extend(['-diff', '-diffdir', config.diffdir])
    subprocess.run(imposm_args, check=True)
    end = datetime.utcnow()
    telemetry_log('import_write', start, end, {'dsn': config.dsn})
    logger.info('Writing OSM tables: DONE')

def import_rotate(config, incremental):
    logger.info('Table rotation: START')
    start = datetime.utcnow()
    imposm_args = [config.imposm, 'import', '-mapping', config.mapping, '-connection', config.dsn, '-srid', '4326', '-deployproduction', '-cachedir', config.cachedir]

    if incremental:
        imposm_args.extend(['-diff', '-diffdir', config.diffdir])
    subprocess.run(imposm_args, check=True)
    end = datetime.utcnow()
    telemetry_log('import_rotate', start, end, {'dsn': config.dsn})
    logger.info('Table rotation: DONE')

def import_extracts(config, extracts, incremental):
    logger.info('Import extracts: START - Processing {0} regions for database import'.format(len(extracts)))
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
        import_extract(config, e, incremental)
    logger.info('Import extracts: DONE')

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
            logger.warning('Database already existed at "{0}"'.format(postgres_dsn))
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
    logger.info('Provision and import: START')
    namespace = os.environ['NAMESPACE']
    kube = SoundscapeKube(None, namespace)
    kube.connect()

    logger.info('Provisioning databases: START')
    for d in kube.enumerate_databases():
        dbstatus = d['dbstatus']

        if dbstatus == None or dbstatus == 'INIT':
            try:
                logger.info('Provisioning database "{0}": START'.format(d['name']))
                kube.set_database_status(d['name'], 'PROVISIONING')
                dsn = d['dsn2']
                dsn_init = d['dsn2'].replace('dbname=osm', 'dbname=postgres')
                provision_database(dsn_init, dsn)
                kube.set_database_status(d['name'], 'PROVISIONED')
                logger.info('Provisioning database "{0}": DONE'.format(d['name']))
            except Exception as e:
                logger.warning('Provisioning database "{0}": FAILED - {1}'.format(d['name'], str(e)))
                kube.set_database_status(d['name'], 'INIT')
    logger.info('Provisioning databases: DONE')

    if updated:
        logger.info('Importing extracts: START')
        import_extracts(config, osm_extracts, False)
        logger.info('Importing extracts: DONE')

    logger.info('Updating databases: START')
    for d in kube.enumerate_databases():
        dbstatus = d['dbstatus']

        if dbstatus != 'PROVISIONED' and dbstatus != 'HASMAPDATA':
            continue

        if dbstatus == 'HASMAPDATA' and not updated:
            logger.info('Skipping database "{0}" - already has map data and no updates'.format(d['name']))
            continue

        try:
            logger.info('Processing database "{0}": START'.format(d['name']))
            args.dsn = kube.get_url_dsn(d['dsn2']) #+ '?sslmode=require'
            import_write(config, False)
            import_rotate(config, False)
            if config.extradatadir:
                logger.info('Importing non-OSM data: START')
                import_non_osm_data(config.extradatadir, d['dsn2'], logger)
                logger.info('Importing non-OSM data: DONE')
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
                    except Exception as e:
                        logger.warning('Failed provisioning database "{0}" - retry {1}: {2}'.format(d['name'], 5-retry_count, str(e)))
                        retry_count -= 1
            logger.info('Processing database "{0}": DONE'.format(d['name']))
        except Exception as e:
            logger.warning('Failed processing database "{0}": {1}'.format(d['name'], str(e)))
    logger.info('Updating databases: DONE')
    logger.info('Provision and import: DONE')

def execute_kube_sync_deployments(manager, desc):
    logger.info('Synchronize {0} with databases: START'.format(desc))
    seen_dbs = []
    for db in manager.enumerate_ready_databases():
        seen_dbs.append(db['name'])

        if not manager.exist_deployment_for_db(db):
            try:
                manager.create_deployment_for_db(db)
                logger.info('Created {0} for "{1}"'.format(desc, db['name']))
            except Exception as e:
                logger.warning('Failed to create {0} for "{1}": {2}'.format(desc, db['name'], str(e)))

    for db in manager.enumerate_deployments():
        if db['name'] not in seen_dbs:
            try:
                manager.delete_deployment_for_db(db)
                logger.info('Deleted {0} for "{1}"'.format(desc, db['name']))
            except Exception as e:
                logger.warning('Failed to delete {0} for "{1}": {2}'.format(desc, db['name'], str(e)))
    logger.info('Synchronize {0} with databases: DONE'.format(desc))

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
    logger.info('Starting ingestion service')
    if config.dynamic_db:
        execute_kube_sync_database_services(config)

    rescan_delay = 60
    initial_import = True
    cycle_count = 0
    
    logger.info('Starting ingestion loop - delay between cycles: {0} seconds ({1:.2f} hours)'.format(config.delay, config.delay/3600))
    if args.where:
        logger.info('Configured regions: {0}'.format([e['name'] for e in osm_extracts]))
    
    while True:
        cycle_count += 1
        cycle_start = datetime.utcnow()
        logger.info('=== INGESTION CYCLE {0} START ==='.format(cycle_count))
        
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
            
            if fetch_delay > 0:
                logger.info('Waiting {0} seconds until next check'.format(min(rescan_delay, fetch_delay)))
                
            time.sleep(rescan_delay)
            fetch_delay -= rescan_delay
        
        cycle_end = datetime.utcnow()
        cycle_duration = cycle_end - cycle_start
        logger.info('=== INGESTION CYCLE {0} COMPLETED in {1} ==='.format(cycle_count, cycle_duration))
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
    logger.info('Starting ingestion engine')
    execute_kube_updatemodel(args)

finally:
    logger.info('Terminating ingestion engine')
    logging.shutdown()
