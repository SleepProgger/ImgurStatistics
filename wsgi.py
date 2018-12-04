'''
Created on Nov 6, 2018

@author: nope
'''

import logging
# TODO: Set from environ 
logging.basicConfig(level=logging.INFO)


from app.app_ import app as application


if __name__ == '__main__':
    application.run(host="0.0.0.0")