'''
Created on Nov 6, 2018

@author: nope
'''

from flask import Flask
import os

app = Flask(__name__, template_folder="templates", static_folder="static")
app.jinja_env.auto_reload = True
app.config['TEMPLATES_AUTO_RELOAD'] = True

import logging
logging.basicConfig(level=logging.INFO)

from app.frontend.routes import *
from app.frontend.api import *


#import json
#print("Starting with environ: %s" % json.dumps(dict(os.environ), indent=2, sort_keys=True), flush=True)

if __name__ == '__main__':
    app.run(host="0.0.0.0")