from .datastructures import MergeDict


def get_long(self, key, default_=None):
    try:
        value = long(self.get(key))
    except:
        return default_
    return value


def get_int(self, key, default_):
    try:
        value = int(self.get(key))
    except:
        return default_
    return value


MergeDict.get_long = get_long
MergeDict.get_int = get_int
