'''
Created on Nov 2, 2018

@author: nope
'''

from gevent_db_pool import AbstractDatabaseConnectionPool
from ImgurApiClient import ImgurApi
import json
from time import time as now
import time

import logging
from psycopg2.extras import DictCursor
import os
logger = logging.getLogger(__name__)
debug = logger.debug
info = logger.info
warn = logger.warn
error = logger.error


_db = None
def get_db(max_cons=5):
    global _db
    if _db is None:
        user = os.environ.get('PG_USER', 'user')
        password = os.environ.get('PG_PASS', '')
        info("Starting DB connection for %s", user)
        _db = DB_Connector("dbname=Imgur", user=user, password=password, maxsize=max_cons)
    return _db
    

class DB_Connector(AbstractDatabaseConnectionPool):
    def __init__(self, *args, maxsize=100, **kwargs):
        AbstractDatabaseConnectionPool.__init__(self, *args, **kwargs)
        self._setup_tables()

    def _setup_tables(self):
        self.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id TEXT PRIMARY KEY,
                userid INT,
                json JSONB,
                all_images_fetched BOOL,
                posted TIMESTAMP WITHOUT TIME ZONE,
                inserted TIMESTAMP DEFAULT (now() at time zone 'utc'),
                last_updated TIMESTAMP DEFAULT (now() at time zone 'utc'),
                
                up INT,
                down INT,
                points INT,
                
                title_tsv TSVECTOR
            )
        """)
        # Textsearch updater and init. Init takes some seconds.
        # TODO: convert strange unicode pages to one default if possible
        if False:
            self.execute("""
                DROP TRIGGER IF EXISTS trigger_posts_update ON posts RESTRICT;
                DROP FUNCTION IF EXISTS update_posts_trigger;
                
                CREATE INDEX IF NOT EXISTS posts_tsv_index ON posts USING GIN (tsv);
                CREATE FUNCTION update_posts_trigger() RETURNS trigger AS $$
                DECLARE
                BEGIN
                  new.tsv := to_tsvector('pg_catalog.english', new.json->>'title');
                  new.up := (new.json->>'ups')::INT;
                  new.down := (new.json->>'downs')::INT;
                  new.points := (new.json->>'points')::INT;
                  return new;
                END
                $$ LANGUAGE plpgsql;
                
                CREATE TRIGGER trigger_posts_update BEFORE INSERT OR UPDATE
                ON posts FOR EACH ROW EXECUTE PROCEDURE
                    update_posts_trigger();
                    
                /* TODO: do manually when required*/
                UPDATE posts SET json=json WHERE tsv IS NULL OR points IS NULL OR up IS NULL OR down IS NULL;
            """)
        
        self.execute("CREATE INDEX IF NOT EXISTS posts_userid_index ON posts (userid)")
        self.execute("CREATE INDEX IF NOT EXISTS posts_posted_index ON posts (posted)")
        self.execute("CREATE INDEX IF NOT EXISTS posts_last_update_index ON posts (last_updated)")
        self.execute("CREATE INDEX IF NOT EXISTS posts_posted_doy_index ON posts ((extract(DOY FROM posted)))")
        self.execute("CREATE INDEX IF NOT EXISTS posts_posted_dow_index ON posts ((extract(DOW FROM posted)))")
        self.execute("CREATE INDEX IF NOT EXISTS posts_posted_hour_index ON posts ((extract(HOUR FROM posted)))")
        self.execute("CREATE INDEX IF NOT EXISTS posts_posted_epoch_index ON posts ((extract(EPOCH FROM posted)))")
        self.execute("CREATE INDEX IF NOT EXISTS posts_posted_epoch_daily_index ON posts (((extract(EPOCH FROM posted) / 86400)::INT))")
        #self.execute("ANALYZE posts;")
        
        self.execute("""
            CREATE TABLE IF NOT EXISTS images (
                id TEXT PRIMARY KEY,
                userid INT,
                postid TEXT,
                json JSONB,
                animated BOOL,
                inserted TIMESTAMP DEFAULT (now() at time zone 'utc'),
                last_updated TIMESTAMP DEFAULT (now() at time zone 'utc')
            )
        """)
        self.execute("CREATE INDEX IF NOT EXISTS images_userid_index ON images (userid)")
        self.execute("CREATE INDEX IF NOT EXISTS images_postid_index ON images (postid)")
        self.execute("CREATE INDEX IF NOT EXISTS images_animated_index ON images (animated)")
        self.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                name TEXT PRIMARY KEY,
                json JSONB,
                inserted TIMESTAMP DEFAULT (now() at time zone 'utc'),
                last_updated TIMESTAMP DEFAULT (now() at time zone 'utc')
            )
        """)
        self.execute("""
            CREATE TABLE IF NOT EXISTS tag_to_post (
                tag_name TEXT,
                postid TEXT,
                primary key (tag_name, postid)
            )
        """)
        self.execute("CREATE INDEX IF NOT EXISTS tag_to_post_tag_name_index ON tag_to_post (tag_name)")
        self.execute("CREATE INDEX IF NOT EXISTS tag_to_post_postid_index ON tag_to_post (postid)")
        
        self.execute("""
            CREATE TABLE IF NOT EXISTS user_names (
                userid INT,
                username TEXT,
                last_seen TIMESTAMP,
                primary key (userid, username)
            )
        """)
        self.execute("CREATE INDEX IF NOT EXISTS user_names_username_lower_index ON user_names (lower(username));")
        self._matviews = dict() 
        self._create_matviews()
        #self.update_matviews()
    
    def _create_matview(self, name, stmt, args=None):
        self.execute("SET work_mem = '128MB'; CREATE materialized view IF NOT EXISTS %s as %s" % (name, stmt), args)
        self._matviews[name] = 1
        
    def _create_matviews(self):
        self._create_matview("matview_posts_day", "SELECT count(id) c, (extract(EPOCH FROM posted)/86400)::INT as h FROM posts GROUP BY h ORDER BY h ASC;")
        
        for frame in ('hour', 'dow'):
            self._create_matview("matview_points_per_%s" % frame, """
                SELECT
                    avg((json->>'points')::NUMERIC)::INT AS a,
                    avg((json->>'ups')::NUMERIC)::INT AS u,
                    avg((json->>'downs')::NUMERIC)::INT AS d,
                    count(id) AS c,
                    extract('%s' FROM posted) AS h
                FROM posts GROUP by h ORDER BY h
            """ % frame)
        
        for since in (1, 7, 30, 365, 365*50):    
            self._create_matview("matview_top_title_since_%d" % since, """
                SELECT a, count(distinct postid) c, sum(p) p FROM (
                    SELECT id as postid, points AS p, unnest(tsvector_to_array(tsv)) a
                        FROM posts
                        WHERE posted > (now() - '%(since)s days'::interval)::date  
                ) XXX                                                    
                WHERE char_length(a) > 2
                GROUP BY a
                ORDER BY p DESC
                LIMIT 1000
            """, {'since': since})
            
            self._create_matview("matview_top_user_since_%d" % since, """
                SELECT uid, username, c, p, a FROM (
                    SELECT uid, count(uid) AS c, sum(points) AS p, avg(points) AS a FROM (
                        SELECT userid AS uid, points AS points FROM posts
                            WHERE posted > (now() - '%(since)s days'::interval)::date
                            AND userid IS NOT NULL
                            AND json->>'account_url' IS NOT NULL
                    ) xx
                    GROUP BY uid
                    ORDER BY p DESC
                    LIMIT 500
                ) xxx JOIN (SELECT username, userid, max(last_seen) FROM user_names GROUP BY userid, username) xxxx ON userid = xxx.uid         
                ORDER BY p DESC
            """, {'since': since})
               
    def update_matview(self, view):
        self.execute("REFRESH MATERIALIZED VIEW %s" % view)
    
    def update_matviews(self):
        for m in self._matviews:
            self.update_matview(m)
            
               
               
    def _cacher(self, _iter, function, *args, commit_after=50, **kwargs):
        """
        Simple utils function to do bulk inserts in using one commit
        """
        cache = []
        i = 0
        try:
            for d in _iter:
                cache.append(d)
                if len(cache) > commit_after:
                    with self.cursor() as c:
                        for d in cache:
                            i += 1
                            function(d, *args, cursor=c, **kwargs)
                    cache = []
        except:
            warn("Exception when using _cacher. Save data (%i) fetched before." % len(cache))
            with self.cursor() as c:
                for d in cache:
                    i += 1
                    function(d, *args, cursor=c, **kwargs)
                raise
        with self.cursor() as c:
            for d in cache:
                i += 1
                function(d, *args, cursor=c, **kwargs)
        info("Found %i items" % i)               
               
               
    def upsert_post(self, post, insert_images=True, cursor=None):
        e = self.execute if cursor is None else cursor.execute
        tags = post.get('tags')
        images = post.get('images', [])
        if 'tags' in post: del post['tags']
        if 'images' in post: del post['images']
        e("""
            INSERT INTO posts (id, userid, json, all_images_fetched, posted) VALUES (%(id)s, %(userid)s, %(json)s, %(images_fetched)s, to_timestamp(%(posted)s))
            ON CONFLICT (id)
            DO UPDATE
                SET json = %(json)s, last_updated =  to_timestamp(%(last_updated)s)
        """, { 
            'id': post['id'], 'userid': post['account_id'], 'json': json.dumps(post),
            'images_fetched': post.get('images_count', 0) == len(images),
            'last_updated': now(), 'posted': post['datetime']
        })
        if "account_url" in post and post['account_url']:
            e("""
                INSERT INTO user_names VALUES (%(id)s, %(name)s, to_timestamp(%(posted)s))
                ON CONFLICT (userid, username) DO UPDATE
                    SET last_seen = GREATEST(user_names.last_seen, EXCLUDED.last_seen)
            """, {'id': post['account_id'], 'name': post['account_url'], 'posted': post['datetime']}
            )       
        if not insert_images:
            return
        if len(images) == 0: # Is a post which isn't an album, so we just save it in posts AND images
            images = [post]
        for image in images:
            self.upsert_image(image, post['account_id'], post['id'], cursor=cursor)
        for tag in tags:
            self.upsert_tag(tag, post['id'], cursor)

    def upsert_image(self, image, userid, postid, cursor=None):
        e = self.execute if cursor is None else cursor.execute
        e("""
            INSERT INTO images (id, userid, postid, json, animated) VALUES (%(id)s, %(userid)s, %(postid)s, %(json)s, %(animated)s)
            ON CONFLICT (id)
            DO UPDATE
                SET json = %(json)s, last_updated =  to_timestamp(%(last_updated)s)
        """, { 'id': image['id'], 'userid': userid, 'postid': postid, 'json': json.dumps(image), 'animated': image.get('animated'), 'last_updated': now() })

    def upsert_tag(self, tag, postid, cursor=None):
        e = self.execute if cursor is None else cursor.execute
        e("""
            INSERT INTO tags (name, json) VALUES (%(name)s, %(json)s)
            ON CONFLICT (name)
            DO UPDATE
                SET last_updated =  to_timestamp(%(last_updated)s)
        """, {'name': tag['name'], 'json': json.dumps(tag), 'last_updated': now() } )
        e("""
            INSERT INTO tag_to_post (tag_name, postid) VALUES (%(name)s, %(postid)s)
            ON CONFLICT (tag_name, postid) DO NOTHING
        """, {'name': tag['name'], 'postid': postid } )
        


    def get_top_poster(self, days, top_x=10):
        matview = "matview_top_user_since_%d" % days
        if matview in self._matviews and top_x <= 500:
            args = []
            stmt = "SELECT * FROM %s LIMIT %s" % (matview, top_x)
        else:
            stmt = """
                SET work_mem = '128MB';
                SELECT uid, username, c, p, a FROM (
                    SELECT uid, count(uid) AS c, sum(points) AS p, avg(points) AS a FROM (
                        SELECT userid AS uid, points AS points FROM posts
                            WHERE posted > (now() - '%(since)s days'::interval)::date
                            AND userid IS NOT NULL
                            AND json->>'account_url' IS NOT NULL
                    ) xx
                    GROUP BY uid
                    ORDER BY p DESC
                    LIMIT %(limit)s
                ) xxx JOIN (SELECT username, userid, max(last_seen) FROM user_names GROUP BY userid, username) xxxx ON userid = xxx.uid         
                ORDER BY p DESC
            """
            args = {'since': days, 'limit': top_x}
        return self.fetchall(stmt, args, cursor_factory=DictCursor)

    def get_post_count(self):
        return self.fetchone("SELECT count(*) FROM posts")[0]

    def get_oldest_post(self):
        return self.fetchone("SELECT min(posted)::timestamp(0) FROM posts")[0]
    
    def get_tags_count(self):
        return self.fetchone("SELECT count(*) FROM tags")[0]

    def get_usernames_count(self):
        return self.fetchone("SELECT count(username), count(distinct userid) FROM user_names")

    def get_last_update(self):
        return self.fetchone("SELECT max(last_updated)::timestamp(0) FROM posts")[0]

    def get_avg_points_per_x(self, x='hour'):
        # DOW = day of week
        # DOY = day of year
        args = []
        matview = "matview_points_per_%s" % x
        if matview in self._matviews:
            stmt = 'SELECT * FROM %s' % matview
        else:
            # This is slow as heck (multiple seconds depending on posts indexed)
            stmt = """
                SET work_mem = '128MB';
                SELECT avg(points)::NUMERIC)::INT AS a, avg(up)::NUMERIC)::INT AS u, avg(down)::NUMERIC)::INT AS d, count(id) AS c, extract(%s FROM posted) AS h FROM posts GROUP by h ORDER BY h
            """
            args = [x]
        return list(dict(x) for x in self.fetchall(stmt, args, cursor_factory=DictCursor))

    def get_user_id(self, username):
        d = self.fetchone('SELECT userid FROM user_names WHERE lower(username) = %s ORDER BY last_seen DESC LIMIT 1', (username,))
        if d is None: return None
        return d[0]
        
    def get_user_name(self, userid):
        d = self.fetchone('SELECT username FROM user_names WHERE userid = %s ORDER BY last_seen DESC LIMIT 1', (userid,))
        if d is None: return None
        return d[0]

    def get_usernames(self, userid):
        return self.fetchall("SELECT username, last_seen::timestamp(0) FROM user_names WHERE userid = %s ORDER BY last_seen DESC", (userid,))

    def get_user_score_graph(self, userid, frame=86400):
        return self.fetchall("""
            SELECT sum(points) AS p, (extract('epoch' FROM posted)/%s)::INT as f FROM posts WHERE userid=%s GROUP BY f ORDER BY f ASC
        """, (frame, userid))

    def get_top_title_words(self, days, top_x=50):
        # TODO: convert strange unicode pages to one default if possible
        matview = "matview_top_title_since_%d" % days
        if matview in self._matviews:
            stmt = "SELECT * FROM %s LIMIT %d" % (matview, top_x)
            args = []
        else:
            stmt = """
                SELECT a, count(distinct postid) c, sum(p) p FROM (
                    SELECT id as postid, points AS p, unnest(tsvector_to_array(tsv)) a
                        FROM posts
                        WHERE posted > (now() - '%(since)s days'::interval)::date  
                ) XXX                                                    
                WHERE char_length(a) > 2
                GROUP BY a
                ORDER BY p DESC
                LIMIT %(limit)s
            """
            args = {'since': days, 'limit': top_x}        
        return self.fetchall(stmt, args, cursor_factory=DictCursor)

    def get_title_word_graph(self, words):
        # TODO: use count to rank, but also create post_count_indexed cached table to build relative values
        return self.fetchall("""
            SET work_mem = '128MB';
            SELECT 100.0 / matview_posts_day.c * xx.c AS p, matview_posts_day.h  FROM (
                    SELECT count(*) AS c, (extract(EPOCH FROM posted)/86400)::INT as h FROM posts AS po1
                        WHERE to_tsquery(%(words)s) @@ tsv
                        GROUP by h
                ) AS xx
            RIGHT JOIN matview_posts_day ON matview_posts_day.h = xx.h
            ORDER BY matview_posts_day.h ASC
        """, {'words': words})
        



if __name__ == '__main__':
    db = get_db()
    api = ImgurApi()
    
    while True:
        _iter = api.iter_galleries(section="top", window="day", start=0, end=40, delay=7)
        db._cacher(_iter, db.upsert_post, insert_images=True, commit_after=100)
        
        _iter = api.iter_galleries(section="user", window="day", sort="top", start=0, end=40, delay=7)
        db._cacher(_iter, db.upsert_post, insert_images=True, commit_after=100)
        time.sleep(60*30)
    
    
    