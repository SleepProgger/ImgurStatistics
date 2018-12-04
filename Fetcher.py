'''
Created on Nov 3, 2018

@author: nope
'''

from app.DB import get_db
from ImgurApiClient import ImgurApi
import time
from time import sleep
import json

import logging
from os.path import isfile
logger = logging.getLogger("Fetcher")
debug = logger.debug
info = logger.info
warn = logger.warn
error = logger.error

logging.basicConfig(level=logging.INFO)


CONFIG_PATH = "config.cfg"


def load_config():
    if not isfile(CONFIG_PATH):
        warn("Creating new config file")
        c = [
            {
                'section': 'top',
                'sort': 'top',
                'window': 'day',
                'start': 0,
                'end': 40,
                'chunks': [0, 40]
            },
            {
                'section': 'top',
                'sort': 'top',
                'window': 'week',
                'start': 0,
                'end': 100,
                'chunks': [0, 10]
            },
            {
                'section': 'top',
                'sort': 'top',
                'window': 'month',
                'start': 0,
                'end': 100,
                'chunks': [0, 10]
            },
            {
                'section': 'top',
                'sort': 'top',
                'window': 'year',
                'start': 0,
                'end': 100,
                'chunks': [0, 10]
            },
            {
                'section': 'top',
                'sort': 'top',
                'window': 'all',
                'start': 0,
                'end': 10000,
                'chunks': [0, 20]
            }
        ]
        save_config(c)
    with open(CONFIG_PATH, 'r') as fd:
        return json.load(fd)

def save_config(config):
    with open(CONFIG_PATH, 'w') as fp:
        return json.dump(config, fp, indent=2)


def loop():
    db = get_db()
    api = ImgurApi()
    
    while True:
        configs = load_config()
        info("New loop with credits: %s" % api.credits)
        
        db.update_matviews()
        
        for config in configs:
            start, max_iter = config.get('chunks', [0, config['end']])
            if start == config['end']: start = 0
            nconfig = dict(config.items())
            del nconfig['chunks']
            end = min(config['end'], start + max_iter)
            nconfig['start'] = start
            nconfig['end'] = end
            
            info("Fetching %s (sort: %s) of %s %i - %i." % (nconfig['section'], nconfig['sort'], nconfig['window'], nconfig['start'], nconfig['end']))
            o_count = - db.get_post_count()
            _iter = api.iter_galleries(delay=6, **nconfig)
            db._cacher(_iter, db.upsert_post, insert_images=True, commit_after=50)    
            o_count += db.get_post_count()
            info("Found %i new posts." % o_count)
            
            if 'chunks' in config:
                config['chunks'][0] = end
                save_config(configs)
                
        db.update_matviews()
        time.sleep(60*20)


if __name__ == '__main__':
    info("Starting up")
    while True:
        try:
            loop()
        except Exception as e:
            error("Last hope catcher got exception.")
            logger.exception(e)
            info("Sleeping for 10 minutes before starting again.")
            sleep(60*10)
            
            
    
    
    