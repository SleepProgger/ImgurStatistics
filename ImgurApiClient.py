'''
Created on Nov 2, 2018

@author: nope
'''
import time
import json
from werkzeug.wsgi import responder
import os

CLIENT_ID = os.environ.get('IMGUR_API_KEY', None)
USE_GEVENT = True
if USE_GEVENT:
    from gevent.time import sleep
else:
    from time import sleep
    
import requests
import logging
logger = logging.getLogger(__name__)
debug = logger.debug
info = logger.info
warn = logger.warn
error = logger.error


class FailedFetchingException(Exception):
    def __init__(self, endpoint):
        Exception.__init__(self, "Failed fetching '%s'" % endpoint)

    
# Simple imgur API. Only supports get, because at this point i don't need more
# TODO: rewrite this properly, or for imgurpython thingy and fix all the old stuff
# TODO:  handle not successfull response properly
class ImgurApi():
    def __init__(self):
        self.headers = {
            'Authorization': 'Client-ID ' + CLIENT_ID,
            'Accept': 'application/json'
        }
        self.credits = None
        self.credits = self.get_credits()
        print("Init with credits: %s" % self.credits)
        
    def _request(self, endpoint, retries=5, delay=30, ignore_credits=False):
        if not ignore_credits:
            api_credits = self.credits
            if api_credits['UserRemaining'] <= 10 and api_credits['UserReset'] - time.time() > -60: # just to be sure
                s = api_credits['UserReset'] - time.time() + 60
                warn("Waiting %i seconds till UserRemaining credits are reset." % (s))
                sleep(s)
                return self._request(endpoint, retries, delay, ignore_credits)
            while api_credits['ClientRemaining'] <= 20:
                warn("Waiting an hour till ClientRemaining credits are reset.")
                sleep(60*60)
                api_credits = self.get_credits()        
        for i in range(retries):
            debug("Requesting '%s'. Retry: %i" % (endpoint, i))
            if self.credits: debug("Credits: %s" % self.credits)
            if i > 0: sleep(i * delay)
            # TODO: try catch all the possible request exceptions
            try:
                data = requests.request("GET", "https://api.imgur.com/3/%s" % endpoint, headers=self.headers)
            except Exception as e:
                error("Exception fetching '%s' : %s" % (endpoint, e))
                continue
            if data.status_code >= 400:
                error("Bad status code (%s) fetching '%s'" % (data.status_code, endpoint))
                continue
            for k, v in data.headers.items():
                if k.startswith('X-RateLimit-'):
                    #print("Update %s header: %s" % (k.replace("X-RateLimit-", ""), int(v)))
                    self.credits[k.replace("X-RateLimit-", "")] = int(v)
            return data.json()
        raise FailedFetchingException(endpoint)
                
    def get_credits(self):
        return self._request("credits", ignore_credits=True).get('data')
 
    def get_gallery(self, section="hot", sort="viral", window="day", page=0, viral=True, mature=True, previews=True):
        if section == "top": # According to docs it should always look like this. According to python-imgur it shouldn't....
            url = 'gallery/{section}/{sort}/{window}/{page}?showViral={viral}&mature={mature}&album_previews={previews}'.format(
            #url = 'gallery/{section}/{window}/page/{page}?showViral={viral}&mature={mature}&album_previews={previews}'.format(
              section=section, sort=sort,
              window=window, page=page,
              viral=str(viral).lower(),
              mature=str(mature).lower(),
              previews=str(previews).lower()            
            )
        else:
            url = 'gallery/{section}/{sort}/{page}?showViral={viral}&mature={mature}&album_previews={previews}'.format(
              section=section, sort=sort,
              page=page,
              viral=str(viral).lower(),
              mature=str(mature).lower(),
              previews=str(previews).lower()            
            ) 
        d = self._request(url)['data']
        debug("Gallery response count: %i" % len(d))
        return d
        
        
    def iter_galleries(self, start=0, end=None, delay=None, **kwargs):
        i = start
        o = None
        while True:
            resp = self.get_gallery(page=i, **kwargs)
            if len(resp) == 0:
                break
            o2 = json.dumps(resp)
            if o == o2:
                warn("Page: %i and %i return the same results" % (i-1, i))
                break
            debug("Points is %i" % resp[0]['points'])
            debug("Score is %i" % resp[0]['score'])
            debug("Ups is %i" % resp[0]['ups'])
            #if min_points and resp[0]['points'] < min_points:
            #    info("Stop at page %i because points is less than %i" % (i, min_points))
            #    break                
            for d in resp:
                yield d            
            i += 1
            if end and i > end:
                break
            if delay:
                sleep(delay)

if __name__ == '__main__':
    api = ImgurApi()
    print(api.credits)
    #print(json.dumps( api._request("gallerya/top?album_previews=false") , indent=2))
    print(api.credits)
    
    for i, data in enumerate(api.iter_galleries(section="top", window="week")):
        #print("Got one: %s" % data)
        print(data['id'])
    
    