from rq import Queue
from redis import Redis

def get_redis():
    return Redis(host="localhost", port=6379, db=0)

def get_queue():
    return Queue("skillsight", connection=get_redis())
