'''
Created on Nov 3, 2018

@author: nope
'''

from app.DB import get_db
 
from flask import Flask
from flask.templating import render_template
import werkzeug
from flask.globals import request
import json

from app.app_ import app 
from werkzeug.exceptions import NotFound
from app.utils import cache

import logging
logger = logging.getLogger(__name__)
debug = logger.debug
info = logger.info
warn = logger.warn
error = logger.error


_flookup = {'day': 1, 'week': 7, 'month': 30, 'year': 365, 'all': 365*50}
_ftitle = {'day': 'Top poster today', 'week': 'Top poster this week', 'month': 'Top poster this month', 'year': 'Top poster this year', 'all': 'Top poster of all time'}
_ftitle_words = {'day': 'Top title words today', 'week': 'Top title words this week', 'month': 'Top title words this month', 'year': 'Top title words this year', 'all': 'Top title words of all time'}

@app.route("/top_user")
@app.route("/top_user/<frame>")
@cache(60*30)
def render_user(frame='day'):
    if not frame in _flookup:
        return NotFound()
    db = get_db()
    args = {
        'timeframe': frame,
        'data': db.get_top_poster(_flookup[frame], 25),
        'titles': _ftitle
    }
    return render_template('top_user.html', **args)

@app.route("/top_title")
@app.route("/top_title/<frame>")
@cache(60*60)
def render_tope_title(frame='day'):
    if not frame in _flookup:
        return NotFound()
    db = get_db()
    args = {
        'timeframe': frame,
        'data': db.get_top_title_words(_flookup[frame], 50),
        'titles': _ftitle_words
    }
    return render_template('top_title.html', **args)

@app.route("/")
def render_index():
    return render_template('index.html')

@app.route("/stats")
@cache(60*60)
def render_stats():
    db = get_db()
    args = {
        'posts_indexed': db.get_post_count(),
        'usernames_indexed': db.get_usernames_count(),
        'oldest_post': db.get_oldest_post(),
        'tags_indexed': db.get_tags_count(),
        'last_update': db.get_last_update()
    }
    return render_template('stats.html', **args)

@app.route("/best_to_post")
@cache(60*60)
def render_best_to_post():
    db = get_db()
    args = {
        'hour_stats': db.get_avg_points_per_x('hour'),
        'day_stats': db.get_avg_points_per_x('dow')
    }
    return render_template('best_to_post.html', **args)

@app.route("/user/<username>")
@app.route("/user/id/<userid>")
@app.route("/user/")
@app.route("/user")
@cache(60*60)
def render_user_info(username=None, userid=None):
    db = get_db()
    warn("Request url: %s" % request.url)
    if "?" in request.url and 'username' in request.args:
        username = request.args['username']    
    if not username and not userid:
        return render_template('user.html', has_user=False)
    if userid is None:
        userid = db.get_user_id(username.lower())
    if username is None:
        username = db.get_user_name(userid)
    err = None
    if username is None:
        err = "No username found for user with id = %s" % userid
    elif userid is None:
        err = "No userid found for user with name = %s" % username
    args = {
        'has_user': True,
        'err': err,
        'username': username,
        'userid': userid,
        'points': {'frame': 86400, 'data': db.get_user_score_graph(userid, 86400)}
    }
    if not err:
        args['user_names'] = db.get_usernames(userid)
    return render_template('user.html', **args)

@app.route("/title_word_graph")
@cache(60*60*24)
def render_title_word_graph(username=None, userid=None):
    db = get_db()
    # TODO: only allow up to x | and & and max length
    searches = []
    for i in range(5):
        w = request.args.get("words%i" % i)
        if w and len(w.strip()):
            searches.append(w.replace(" ", "+")) 
    
    info("Searches %s" % searches)
    
    #frame = 86400 * 7
    frame = 60 * 60 * 24
    # TODO: catch sysntax error in search term 
    args = {
        'data': [{'frame': frame, 'search': x, 'data': db.get_title_word_graph(x)} for x in searches]
    }
    return render_template('title_word_graph.html', **args)
